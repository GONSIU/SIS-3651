from django.db import models
from apps.core.models import TimeStampedModel

class Terminal(TimeStampedModel):
    nombre = models.CharField(max_length=100)
    ciudad = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200, blank=True)
 
    class Meta:
        ordering = ["ciudad", "nombre"]
 
    def __str__(self):
        return f"{self.nombre} ({self.ciudad})"
 
 
class Ruta(TimeStampedModel):
    origen = models.ForeignKey(
        Terminal, related_name="rutas_origen", on_delete=models.PROTECT
    )
    destino = models.ForeignKey(
        Terminal, related_name="rutas_destino", on_delete=models.PROTECT
    )
    distancia_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    duracion_minutos = models.PositiveIntegerField(null=True, blank=True)
    activa = models.BooleanField(default=True)
 
    class Meta:
        ordering = ["origen__ciudad", "destino__ciudad"]
 
    def __str__(self):
        return f"{self.origen} → {self.destino}"
 
 
class Horario(TimeStampedModel):
    ruta = models.ForeignKey(Ruta, related_name="horarios", on_delete=models.CASCADE)
    hora_salida = models.TimeField()
    dias_semana = models.CharField(max_length=20, help_text="Ej. L,M,X,J,V,S,D")
 
    class Meta:
        ordering = ["ruta", "hora_salida"]
        constraints = [
            models.UniqueConstraint(
                fields=["ruta", "hora_salida"], name="uniq_horario_ruta_hora"
            )
        ]
 
    def __str__(self):
        return f"{self.ruta} — {self.hora_salida}"
