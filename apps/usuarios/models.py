from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    ROL_CHOICES = [
        ("cliente", "Cliente"),
        ("ventanillero", "Ventanillero"),
        ("supervisor", "Supervisor"),
        ("admin", "Administrador"),
    ]

    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default="cliente")
    telefono = models.CharField(max_length=20, blank=True)
    ci = models.CharField(max_length=20, unique=True, null=True, blank=True)

    # Descomenta esta relación una vez que definas el modelo Terminal
    # en apps/rutas/models.py (útil para asignar ventanilleros a una terminal):
    #
    # terminal_asignado = models.ForeignKey(
    #     "rutas.Terminal", null=True, blank=True, on_delete=models.SET_NULL
    # )

    def __str__(self):
        return self.get_full_name() or self.username
