from django.conf import settings
from django.db import models
from apps.rutas.models import Ruta, Horario
from apps.flota.models import Bus, Asiento


class Viaje(models.Model):
    ESTADO_CHOICES = [
        ("programado", "Programado"),
        ("en_curso", "En Curso"),
        ("retrasado", "Retrasado"),
        ("completado", "Completado"),
        ("cancelado", "Cancelado"),
    ]

    ruta = models.ForeignKey(Ruta, related_name="viajes", on_delete=models.PROTECT)
    horario = models.ForeignKey(Horario, related_name="viajes", on_delete=models.PROTECT)
    bus = models.ForeignKey(Bus, related_name="viajes", on_delete=models.PROTECT)
    # conductor: se agrega cuando exista apps.personal.Empleado
    fecha_salida = models.DateField()
    hora_salida_real = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="programado")
    minutos_retraso = models.PositiveIntegerField(default=0)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="viajes_creados",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="viajes_actualizados",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_salida", "horario"]
        constraints = [
            models.UniqueConstraint(
                fields=["bus", "fecha_salida", "horario"], name="uniq_viaje_bus_fecha_horario"
            )
        ]

    def __str__(self):
        return f"{self.ruta} — {self.fecha_salida} ({self.bus.placa})"

    @property
    def asientos_totales(self):
        return self.asientos_viaje.count()

    @property
    def asientos_vendidos(self):
        return self.asientos_viaje.filter(estado="vendido").count()

    def crear_asientos_desde_bus(self):
        """Genera un AsientoViaje 'disponible' por cada Asiento físico del bus asignado.
        Se llama al crear el viaje (o desde el admin) para inicializar el mapa de asientos."""
        asientos_viaje = [
            AsientoViaje(viaje=self, asiento=asiento)
            for asiento in self.bus.asientos.all()
        ]
        AsientoViaje.objects.bulk_create(asientos_viaje, ignore_conflicts=True)


class AsientoViaje(models.Model):
    ESTADO_CHOICES = [
        ("disponible", "Disponible"),
        ("reservado", "Reservado"),
        ("vendido", "Vendido"),
        ("bloqueado", "Bloqueado"),
    ]

    viaje = models.ForeignKey(Viaje, related_name="asientos_viaje", on_delete=models.CASCADE)
    asiento = models.ForeignKey(Asiento, related_name="asientos_viaje", on_delete=models.PROTECT)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="disponible")

    class Meta:
        ordering = ["asiento__piso", "asiento__fila", "asiento__columna"]
        constraints = [
            models.UniqueConstraint(
                fields=["viaje", "asiento"], name="uniq_asientoviaje_viaje_asiento"
            )
        ]

    def __str__(self):
        return f"{self.viaje} — Asiento {self.asiento.numero} ({self.estado})"
    