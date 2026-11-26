from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Notificacion
from apps.core.utils import generar_codigo
from apps.core.validators import normalizar_espacios


# A nivel de modulo: las comprensiones dentro de class Meta no ven los atributos de la clase.
CATEGORIA_CHOICES = [
    ("falla_mecanica", "Falla mecanica"),
    ("retraso", "Retraso operativo"),
    ("dano_unidad", "Dano en unidad"),
    ("accidente", "Accidente"),
    ("otro", "Otro"),
    ("reclamo", "Reclamo de cliente"),
    ("sugerencia", "Comentario o sugerencia"),
]
ESTADO_CHOICES = [
    ("abierta", "Abierta"),
    ("en_revision", "En revision"),
    ("resuelta", "Resuelta"),
]


class Incidencia(models.Model):
    """Incidente operativo o reclamo de un cliente, con seguimiento hasta resolverlo.

    Es una sola tabla, como la clase Incidencia del diagrama de dominio: la categoria
    distingue lo que registra el personal (falla mecanica, retraso...) de lo que envia el
    cliente (reclamo o sugerencia). El estado solo avanza con cambiar_estado()."""

    CATEGORIA_CHOICES = CATEGORIA_CHOICES
    # Categorias que puede elegir un cliente desde su cuenta.
    CATEGORIAS_CLIENTE = ("reclamo", "sugerencia")

    ESTADO_CHOICES = ESTADO_CHOICES
    # Resuelta es final. "En revision" equivale a escalar la incidencia.
    TRANSICIONES: dict[str, tuple[str, ...]] = {
        "abierta": ("en_revision", "resuelta"),
        "en_revision": ("resuelta",),
        "resuelta": (),
    }
    ESTADOS_PENDIENTES = ("abierta", "en_revision")
    # Margen para relojes desfasados al validar que ocurrido_en no este en el futuro.
    TOLERANCIA_FUTURO = timedelta(minutes=5)

    codigo = models.CharField(max_length=20, unique=True, blank=True)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES)
    titulo = models.CharField(max_length=120)
    descripcion = models.TextField(max_length=2000)
    ocurrido_en = models.DateTimeField(default=timezone.now)
    viaje = models.ForeignKey(
        "viajes.Viaje", null=True, blank=True, on_delete=models.SET_NULL, related_name="incidencias"
    )
    bus = models.ForeignKey(
        "flota.Bus", null=True, blank=True, on_delete=models.SET_NULL, related_name="incidencias"
    )
    pasaje = models.ForeignKey(
        "ventas.Pasaje", null=True, blank=True, on_delete=models.SET_NULL, related_name="reclamos"
    )
    empleado_involucrado = models.ForeignKey(
        "personal.Empleado", null=True, blank=True, on_delete=models.SET_NULL, related_name="incidencias"
    )
    # Evaluacion del servicio (1 a 5) que deja el cliente; opcional.
    calificacion = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="abierta")
    resolucion = models.TextField(max_length=2000, blank=True)
    reportado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="incidencias_reportadas"
    )
    resuelta_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incidencias_resueltas",
    )
    resuelta_en = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                check=Q(categoria__in=[clave for clave, _ in CATEGORIA_CHOICES]),
                name="incidencia_categoria_valida",
                violation_error_message="Categoria no valida.",
            ),
            models.CheckConstraint(
                check=Q(estado__in=[clave for clave, _ in ESTADO_CHOICES]),
                name="incidencia_estado_valido",
                violation_error_message="Estado no valido.",
            ),
            models.CheckConstraint(
                check=Q(calificacion__isnull=True) | Q(calificacion__gte=1, calificacion__lte=5),
                name="incidencia_calificacion_1_a_5",
                violation_error_message="La calificacion debe estar entre 1 y 5.",
            ),
            models.CheckConstraint(
                check=~Q(estado="resuelta") | ~Q(resolucion=""),
                name="incidencia_resuelta_con_resolucion",
                violation_error_message="Una incidencia resuelta necesita la resolucion.",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.titulo}"

    @property
    def es_de_cliente(self) -> bool:
        return self.categoria in self.CATEGORIAS_CLIENTE

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = generar_codigo("RCL" if self.es_de_cliente else "INC")
        # El viaje y el bus se deducen del pasaje o del viaje si no se indicaron.
        if self.pasaje_id and not self.viaje_id:
            self.viaje_id = self.pasaje.viaje_id
        if self.viaje_id and not self.bus_id:
            self.bus_id = self.viaje.bus_id
        super().save(*args, **kwargs)

    def clean_fields(self, exclude=None):
        self.titulo = normalizar_espacios(self.titulo)
        self.descripcion = (self.descripcion or "").strip()
        self.resolucion = (self.resolucion or "").strip()
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        errores: dict[str, list[str]] = {}
        if self._state.adding and self.estado != "abierta":
            errores.setdefault("estado", []).append("Una incidencia nueva empieza abierta.")
        if self.ocurrido_en and self.ocurrido_en > timezone.now() + self.TOLERANCIA_FUTURO:
            errores.setdefault("ocurrido_en", []).append("La fecha del suceso no puede estar en el futuro.")
        if self.calificacion is not None and not self.es_de_cliente:
            errores.setdefault("calificacion", []).append(
                "La calificacion solo se registra en reclamos y sugerencias."
            )
        if self.pasaje_id and self.viaje_id and self.pasaje.viaje_id != self.viaje_id:
            errores.setdefault("viaje", []).append("El viaje no coincide con el del pasaje.")
        if errores:
            raise ValidationError(errores)

    @property
    def estados_siguientes(self) -> list[tuple[str, str]]:
        etiquetas = dict(self.ESTADO_CHOICES)
        return [(estado, etiquetas[estado]) for estado in self.TRANSICIONES[self.estado]]

    def cambiar_estado(self, nuevo_estado: str, usuario, resolucion: str = "") -> None:
        """Valida la transicion; para resolver exige el texto de la resolucion. Si la
        reporto un cliente, le llega una notificacion con el nuevo estado."""
        if nuevo_estado not in self.TRANSICIONES:
            raise ValidationError("Estado no valido.")
        if nuevo_estado not in self.TRANSICIONES[self.estado]:
            etiquetas = dict(self.ESTADO_CHOICES)
            raise ValidationError(
                f"No se puede pasar de {etiquetas[self.estado].lower()} a {etiquetas[nuevo_estado].lower()}."
            )
        campos = ["estado", "updated_at"]
        if nuevo_estado == "resuelta":
            resolucion = (resolucion or "").strip()
            if not resolucion:
                raise ValidationError("Escribe la resolucion para cerrar la incidencia.")
            self.resolucion = resolucion
            self.resuelta_por = usuario
            self.resuelta_en = timezone.now()
            campos += ["resolucion", "resuelta_por", "resuelta_en"]
        self.estado = nuevo_estado
        self.save(update_fields=campos)
        self._avisar_al_cliente()

    def _avisar_al_cliente(self) -> None:
        if getattr(self.reportado_por, "rol", None) != "cliente":
            return
        nombre = "reclamo" if self.categoria == "reclamo" else "comentario"
        if self.estado == "resuelta":
            titulo = f"Tu {nombre} fue respondido"
            mensaje = f"Ticket {self.codigo}: {self.resolucion}"
        else:
            titulo = f"Tu {nombre} esta en revision"
            mensaje = f"Ticket {self.codigo}: el equipo de Trans Naser esta revisando tu caso."
        Notificacion.avisar(self.reportado_por_id, titulo, mensaje, reverse("incidencias:mis_reclamos"))
