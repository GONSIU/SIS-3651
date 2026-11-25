from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .validators import validar_fecha_no_futura

# A nivel de modulo porque Meta (clase anidada) no ve los atributos de Empleado.
CARGO_CHOICES = [
    ("ventanillero", "Ventanillero"),
    ("supervisor", "Supervisor de terminal"),
    ("administrador", "Administrador"),
    ("conductor", "Conductor"),
    ("encargado_encomiendas", "Encargado de encomiendas"),
    ("ayudante_bus", "Ayudante de bus"),
]


class Empleado(models.Model):
    """Ficha laboral de un usuario del sistema.

    El terminal no se guarda aqui: se usa usuario.terminal_asignado para no tener
    el mismo dato en dos tablas.

    cargo es el puesto laboral y Usuario.rol el permiso en el sistema. No son lo mismo,
    pero no cualquier combinacion tiene sentido: CARGOS_POR_ROL dice que cargos admite
    cada rol (los operativos, sin pantallas propias, usan el rol mas cercano)."""

    CARGO_CHOICES = CARGO_CHOICES
    # Claves: Usuario.ROL_CHOICES (sin "cliente", que no es personal). El primer cargo de
    # cada rol es el que se usa por defecto.
    CARGOS_POR_ROL: dict[str, tuple[str, ...]] = {
        "ventanillero": ("ventanillero", "encargado_encomiendas"),
        "supervisor": ("supervisor",),
        "admin": ("administrador",),
        "conductor": ("conductor", "ayudante_bus"),
    }

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="empleado"
    )
    cargo = models.CharField(max_length=50, choices=CARGO_CHOICES)
    fecha_ingreso = models.DateField(validators=[validar_fecha_no_futura])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "empleados"
        ordering = ["usuario__first_name", "usuario__last_name", "usuario__username"]
        constraints = [
            # choices solo se valida con full_clean(); esto lo garantiza en la base de datos.
            models.CheckConstraint(
                check=Q(cargo__in=[clave for clave, _ in CARGO_CHOICES]),
                name="empleado_cargo_valido",
                violation_error_message="El cargo no esta en la lista de cargos.",
            )
        ]

    def __str__(self):
        return f"{self.usuario} — {self.get_cargo_display()}"

    @classmethod
    def cargos_para_rol(cls, rol: str) -> tuple[str, ...]:
        return cls.CARGOS_POR_ROL.get(rol, ())

    def clean(self):
        super().clean()
        if self.usuario_id and self.cargo:
            permitidos = self.cargos_para_rol(self.usuario.rol)
            if self.cargo not in permitidos:
                nombres = dict(self.CARGO_CHOICES)
                opciones = ", ".join(nombres[c] for c in permitidos) or "ninguno"
                raise ValidationError(
                    {
                        "cargo": f"Con rol {self.usuario.get_rol_display()} el cargo puede ser: "
                        f"{opciones}."
                    }
                )

    @property
    def terminal(self):
        return self.usuario.terminal_asignado
