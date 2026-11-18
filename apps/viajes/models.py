from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
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
    # Estados a los que se puede pasar desde cada estado. Completado y cancelado son
    # finales. retrasado -> retrasado permite corregir la estimacion del retraso.
    TRANSICIONES: dict[str, tuple[str, ...]] = {
        "programado": ("retrasado", "en_curso", "cancelado"),
        "retrasado": ("retrasado", "en_curso", "cancelado"),
        "en_curso": ("completado",),
        "completado": (),
        "cancelado": (),
    }
    # Un viaje en estos estados ya no vende pasajes ni recibe encomiendas.
    ESTADOS_SIN_VENTA = ("en_curso", "completado", "cancelado")
    MAX_MINUTOS_RETRASO = 24 * 60

    ruta = models.ForeignKey(Ruta, related_name="viajes", on_delete=models.PROTECT)
    horario = models.ForeignKey(Horario, related_name="viajes", on_delete=models.PROTECT)
    bus = models.ForeignKey(Bus, related_name="viajes", on_delete=models.PROTECT)
    # Opcional para no romper los viajes programados antes de existir el rol conductor.
    # PROTECT: un conductor con viajes no se borra; se desactiva su usuario.
    conductor = models.ForeignKey(
        "personal.Empleado",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="viajes_conducidos",
    )
    fecha_salida = models.DateField()
    hora_salida_real = models.DateTimeField(null=True, blank=True)
    # Se registra al marcar la llegada (registrar_llegada). Junto con hora_salida_real
    # permite reportes de duracion real y puntualidad.
    hora_llegada_real = models.DateTimeField(null=True, blank=True)
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
            models.CheckConstraint(
                check=Q(hora_llegada_real__isnull=True)
                | Q(hora_salida_real__isnull=False, hora_llegada_real__gte=F("hora_salida_real")),
                name="viaje_llegada_despues_de_salida",
                violation_error_message="La llegada debe registrarse despues de la salida.",
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

        if self.conductor_id:
            if self._conductor_es_nuevo():
                usuario = self.conductor.usuario
                if usuario.rol != "conductor":
                    errores.setdefault("conductor", []).append("El empleado elegido no tiene rol de conductor.")
                elif not usuario.is_active:
                    errores.setdefault("conductor", []).append("El conductor elegido esta inactivo.")
            if self.horario_id and self.fecha_salida and self._conductor_ocupado():
                errores.setdefault("conductor", []).append(
                    "El conductor ya tiene un viaje ese dia a esa hora."
                )

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

    def _conductor_es_nuevo(self) -> bool:
        """Indica si el viaje se esta creando o si cambia el conductor guardado.

        Asi un viaje antiguo se puede editar aunque su conductor ya no tenga el rol."""
        if self._state.adding:
            return True
        return Viaje.objects.filter(pk=self.pk).exclude(conductor_id=self.conductor_id).exists()

    def _conductor_ocupado(self) -> bool:
        """Busca otro viaje no cancelado del mismo conductor ese dia a la misma hora.

        No detecta solapamientos (un viaje largo y otro que sale antes de que termine):
        ver docs/validaciones.md."""
        if self.estado == "cancelado":
            return False
        return (
            Viaje.objects.filter(
                conductor_id=self.conductor_id,
                fecha_salida=self.fecha_salida,
                horario__hora_salida=self.horario.hora_salida,
            )
            .exclude(estado="cancelado")
            .exclude(pk=self.pk)
            .exists()
        )

    # --- Control operativo -------------------------------------------------------
    # Igual que Encomienda.cambiar_estado(): el estado solo cambia por estos metodos,
    # que validan la transicion y guardan solo los campos que tocan. La vista bloquea
    # el viaje con select_for_update() antes de llamarlos.

    @property
    def salida_programada(self) -> datetime:
        """Fecha y hora de salida segun el horario, en la zona horaria del proyecto."""
        return timezone.make_aware(datetime.combine(self.fecha_salida, self.horario.hora_salida))

    @property
    def estados_siguientes(self) -> tuple[str, ...]:
        return self.TRANSICIONES[self.estado]

    def _validar_transicion(self, nuevo_estado: str) -> None:
        if nuevo_estado not in self.TRANSICIONES[self.estado]:
            etiquetas = dict(self.ESTADO_CHOICES)
            raise ValidationError(
                f"No se puede pasar de {etiquetas[self.estado].lower()} a {etiquetas[nuevo_estado].lower()}."
            )

    def _guardar_estado(self, nuevo_estado: str, usuario, *campos: str) -> None:
        self.estado = nuevo_estado
        self.actualizado_por = usuario
        self.save(update_fields=["estado", "actualizado_por", "updated_at", *campos])

    def marcar_retraso(self, minutos: int, usuario) -> None:
        """Registra un retraso estimado antes de la salida. Se puede volver a llamar
        para corregir la estimacion."""
        self._validar_transicion("retrasado")
        if not 1 <= minutos <= self.MAX_MINUTOS_RETRASO:
            raise ValidationError(f"El retraso debe estar entre 1 y {self.MAX_MINUTOS_RETRASO} minutos.")
        self.minutos_retraso = minutos
        self._guardar_estado("retrasado", usuario, "minutos_retraso")

    def registrar_salida(self, usuario, momento: datetime | None = None) -> None:
        """Marca la salida real. El retraso pasa a ser el real (0 si salio a tiempo o
        antes), reemplazando la estimacion de marcar_retraso()."""
        self._validar_transicion("en_curso")
        momento = momento or timezone.now()
        if timezone.localdate(momento) < self.fecha_salida:
            raise ValidationError("Aun no es el dia de salida de este viaje.")
        segundos_tarde = (momento - self.salida_programada).total_seconds()
        self.minutos_retraso = max(0, int(segundos_tarde // 60))
        self.hora_salida_real = momento
        self._guardar_estado("en_curso", usuario, "minutos_retraso", "hora_salida_real")

    def registrar_llegada(self, usuario, momento: datetime | None = None) -> None:
        """Marca la llegada real y completa el viaje."""
        self._validar_transicion("completado")
        momento = momento or timezone.now()
        if self.hora_salida_real and momento < self.hora_salida_real:
            raise ValidationError("La llegada no puede ser anterior a la salida registrada.")
        self.hora_llegada_real = momento
        self._guardar_estado("completado", usuario, "hora_llegada_real")

    @property
    def duracion_real_minutos(self) -> int | None:
        """Minutos entre la salida y la llegada reales, o None si falta alguna."""
        if not (self.hora_salida_real and self.hora_llegada_real):
            return None
        return int((self.hora_llegada_real - self.hora_salida_real).total_seconds() // 60)

    def cancelar(self, usuario) -> None:
        """Cancela un viaje que aun no salio. Los pasajes vendidos no se tocan (no hay
        reembolsos); el aviso a los pasajeros llega con las notificaciones."""
        self._validar_transicion("cancelado")
        # La constraint viaje_retraso_segun_estado no admite retraso en un cancelado.
        self.minutos_retraso = 0
        self._guardar_estado("cancelado", usuario, "minutos_retraso")

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
    