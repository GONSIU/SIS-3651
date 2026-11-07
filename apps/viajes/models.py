from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
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
            ),
            models.CheckConstraint(
                check=Q(minutos_retraso=0) | Q(estado__in=["retrasado", "en_curso", "completado"]),
                name="viaje_retraso_segun_estado",
                violation_error_message="Solo un viaje retrasado, en curso o completado puede tener retraso.",
            ),
        ]

    def __str__(self):
        return f"{self.ruta} — {self.fecha_salida} ({self.bus.placa})"

    def clean(self):
        super().clean()
        errores: dict[str, list[str]] = {}

        if self._state.adding and self.fecha_salida and self.fecha_salida < timezone.localdate():
            errores.setdefault("fecha_salida", []).append("La fecha de salida no puede ser pasada.")

        if self.horario_id:
            if self.ruta_id and self.horario.ruta_id != self.ruta_id:
                errores.setdefault("horario", []).append("El horario no pertenece a la ruta elegida.")
            if self.fecha_salida and not self.horario.opera_el(self.fecha_salida):
                errores.setdefault("fecha_salida", []).append(
                    f"El horario no opera ese dia (dias: {self.horario.dias_semana})."
                )

        if self.bus_id:
            if self._bus_es_nuevo() and self.bus.estado != "activo":
                errores.setdefault("bus", []).append("El bus no esta activo.")
            if self.horario_id and self.fecha_salida and self._bus_ocupado():
                errores.setdefault("bus", []).append("El bus ya tiene un viaje ese dia a esa hora.")

        if errores:
            raise ValidationError(errores)

    def _bus_es_nuevo(self) -> bool:
        """Indica si el viaje se esta creando o si cambia el bus guardado."""
        if self._state.adding:
            return True
        return Viaje.objects.filter(pk=self.pk).exclude(bus_id=self.bus_id).exists()

    def _bus_ocupado(self) -> bool:
        """Busca otro viaje no cancelado del bus a la misma hora con otro horario.

        El mismo horario ya lo cubre la constraint uniq_viaje_bus_fecha_horario."""
        if self.estado == "cancelado":
            return False
        return (
            Viaje.objects.filter(
                bus_id=self.bus_id,
                fecha_salida=self.fecha_salida,
                horario__hora_salida=self.horario.hora_salida,
            )
            .exclude(estado="cancelado")
            .exclude(horario_id=self.horario_id)
            .exclude(pk=self.pk)
            .exists()
        )

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
    