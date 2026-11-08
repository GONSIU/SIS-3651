from django.conf import settings
from django.db import models

from apps.core.validators import normalizar_espacios
from .validators import validar_fecha_no_futura


class Empleado(models.Model):
    """Ficha laboral de un usuario del sistema.

    El terminal no se guarda aqui: se usa usuario.terminal_asignado para no tener
    el mismo dato en dos tablas."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="empleado"
    )
    cargo = models.CharField(max_length=50)
    fecha_ingreso = models.DateField(validators=[validar_fecha_no_futura])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "empleados"
        ordering = ["usuario__first_name", "usuario__last_name", "usuario__username"]

    def __str__(self):
        return f"{self.usuario} — {self.cargo}"

    def clean_fields(self, exclude=None):
        self.cargo = normalizar_espacios(self.cargo)
        super().clean_fields(exclude=exclude)

    @property
    def terminal(self):
        return self.usuario.terminal_asignado
