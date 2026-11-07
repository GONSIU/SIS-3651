from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.validators import (
    normalizar_ci,
    normalizar_espacios,
    normalizar_telefono,
    validar_ci,
    validar_nombre_persona,
    validar_telefono,
)


class Usuario(AbstractUser):
    ROL_CHOICES = [
        ("cliente", "Cliente"),
        ("ventanillero", "Ventanillero"),
        ("supervisor", "Supervisor"),
        ("admin", "Administrador"),
    ]
    ROLES_CON_TERMINAL = ("ventanillero", "supervisor")

    first_name = models.CharField(
        _("first name"), max_length=50, blank=True, validators=[validar_nombre_persona]
    )
    last_name = models.CharField(
        _("last name"), max_length=50, blank=True, validators=[validar_nombre_persona]
    )
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default="cliente")
    telefono = models.CharField(max_length=15, blank=True, validators=[validar_telefono])
    ci = models.CharField(max_length=12, unique=True, null=True, blank=True, validators=[validar_ci])

    terminal_asignado = models.ForeignKey(
        "rutas.Terminal",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="empleados_asignados",
    )

    def __str__(self):
        return self.get_full_name() or self.username

    def clean_fields(self, exclude=None):
        self.first_name = normalizar_espacios(self.first_name)
        self.last_name = normalizar_espacios(self.last_name)
        self.telefono = normalizar_telefono(self.telefono)
        # Vacio pasa a NULL: unique permite varios NULL, pero no varios "".
        self.ci = normalizar_ci(self.ci) or None
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        if self.rol in self.ROLES_CON_TERMINAL and not self.terminal_asignado_id:
            raise ValidationError(
                {"terminal_asignado": "Este rol necesita un terminal asignado."}
            )
