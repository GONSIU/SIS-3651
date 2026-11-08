from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.utils import generar_codigo
from apps.core.validators import (
    normalizar_ci,
    normalizar_espacios,
    normalizar_telefono,
    validar_ci,
    validar_nombre_persona,
    validar_telefono,
)
from apps.ventas.models import Pago
from apps.viajes.models import Viaje

CENTAVO = Decimal("0.01")


class Encomienda(models.Model):
    ESTADO_CHOICES = [
        ("registrado", "Registrado"),
        ("en_destino", "En destino"),
        ("entregado", "Entregado"),
        ("extraviado", "Extraviado"),
    ]
    # Estados a los que se puede pasar desde cada estado. Entregado y extraviado son finales.
    TRANSICIONES: dict[str, tuple[str, ...]] = {
        "registrado": ("en_destino", "extraviado"),
        "en_destino": ("entregado", "extraviado"),
        "entregado": (),
        "extraviado": (),
    }
    # Estados que no ocupan espacio en la bodega del bus.
    ESTADOS_SIN_CARGA = ("extraviado",)

    # Tarifa: flete base + cargo por kg + seguro sobre el valor declarado.
    FLETE_BASE = Decimal("10.00")
    TARIFA_POR_KG = Decimal("2.50")
    TASA_SEGURO = Decimal("0.01")

    codigo_guia = models.CharField(max_length=20, unique=True, blank=True)
    viaje = models.ForeignKey(Viaje, related_name="encomiendas", on_delete=models.PROTECT)

    remitente_nombre = models.CharField(max_length=100, validators=[validar_nombre_persona])
    remitente_ci = models.CharField(max_length=12, validators=[validar_ci])
    remitente_telefono = models.CharField(max_length=15, blank=True, validators=[validar_telefono])
    destinatario_nombre = models.CharField(max_length=100, validators=[validar_nombre_persona])
    destinatario_ci = models.CharField(max_length=12, validators=[validar_ci])
    destinatario_telefono = models.CharField(max_length=15, blank=True, validators=[validar_telefono])

    descripcion_contenido = models.CharField(max_length=200)
    peso_kg = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(CENTAVO)]
    )
    valor_declarado = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    fragil = models.BooleanField(default=False)
    foto_paquete = models.ImageField(upload_to="encomiendas/%Y/%m/", blank=True)
    # Se calcula al registrar (ver calcular_tarifa) y no cambia despues: es lo que se cobro.
    precio_envio = models.DecimalField(
        max_digits=8, decimal_places=2, blank=True, validators=[MinValueValidator(CENTAVO)]
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="registrado")

    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="encomiendas_registradas",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="encomiendas_actualizadas",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=Q(peso_kg__gt=0),
                name="encomienda_peso_positivo",
                violation_error_message="El peso debe ser mayor a 0.",
            ),
            models.CheckConstraint(
                check=Q(precio_envio__gt=0),
                name="encomienda_precio_positivo",
                violation_error_message="El precio de envio debe ser mayor a 0.",
            ),
            models.CheckConstraint(
                check=Q(valor_declarado__isnull=True) | Q(valor_declarado__gte=0),
                name="encomienda_valor_declarado_no_negativo",
                violation_error_message="El valor declarado no puede ser negativo.",
            ),
        ]

    def __str__(self):
        return f"{self.codigo_guia} — {self.remitente_nombre} a {self.destinatario_nombre}"

    def save(self, *args, **kwargs):
        if not self.codigo_guia:
            self.codigo_guia = generar_codigo("ENC")
        if self.precio_envio is None and self.peso_kg is not None:
            self.precio_envio = self.calcular_tarifa(self.peso_kg, self.valor_declarado)["total"]
        super().save(*args, **kwargs)

    def clean_fields(self, exclude=None):
        self.remitente_nombre = normalizar_espacios(self.remitente_nombre)
        self.destinatario_nombre = normalizar_espacios(self.destinatario_nombre)
        self.remitente_ci = normalizar_ci(self.remitente_ci)
        self.destinatario_ci = normalizar_ci(self.destinatario_ci)
        self.remitente_telefono = normalizar_telefono(self.remitente_telefono)
        self.destinatario_telefono = normalizar_telefono(self.destinatario_telefono)
        self.descripcion_contenido = normalizar_espacios(self.descripcion_contenido)
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        errores: dict[str, list[str]] = {}

        if self._state.adding:
            if self.estado != "registrado":
                errores.setdefault("estado", []).append("Una encomienda nueva empieza como registrada.")
            if self.viaje_id:
                if self.viaje.estado in ("cancelado", "completado"):
                    errores.setdefault("viaje", []).append(
                        f"No se puede enviar: el viaje esta {self.viaje.get_estado_display().lower()}."
                    )
                elif self.viaje.fecha_salida < timezone.localdate():
                    errores.setdefault("viaje", []).append("No se puede enviar: la fecha de salida ya paso.")
        else:
            anterior = Encomienda.objects.filter(pk=self.pk).values_list("estado", flat=True).first()
            if anterior and anterior != self.estado and self.estado not in self.TRANSICIONES[anterior]:
                errores.setdefault("estado", []).append(self._mensaje_transicion(anterior, self.estado))

        if self.viaje_id and self.peso_kg and self.estado not in self.ESTADOS_SIN_CARGA:
            disponible = self.viaje.bus.capacidad_carga_kg - self._carga_ocupada()
            if self.peso_kg > disponible:
                errores.setdefault("peso_kg", []).append(
                    f"Supera la capacidad de carga del bus (disponible: {max(disponible, 0)} kg)."
                )

        if errores:
            raise ValidationError(errores)

    def _carga_ocupada(self) -> Decimal:
        """Suma el peso de las demas encomiendas del viaje que siguen en la bodega."""
        total = (
            Encomienda.objects.filter(viaje_id=self.viaje_id)
            .exclude(estado__in=self.ESTADOS_SIN_CARGA)
            .exclude(pk=self.pk)
            .aggregate(total=Sum("peso_kg"))["total"]
        )
        return total or Decimal("0")

    def _mensaje_transicion(self, anterior: str, nuevo: str) -> str:
        etiquetas = dict(self.ESTADO_CHOICES)
        return f"No se puede pasar de {etiquetas[anterior].lower()} a {etiquetas[nuevo].lower()}."

    @classmethod
    def calcular_tarifa(cls, peso_kg: Decimal, valor_declarado: Decimal | None) -> dict[str, Decimal]:
        cargo_peso = (peso_kg * cls.TARIFA_POR_KG).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        seguro = ((valor_declarado or Decimal("0")) * cls.TASA_SEGURO).quantize(
            CENTAVO, rounding=ROUND_HALF_UP
        )
        return {
            "flete_base": cls.FLETE_BASE,
            "cargo_peso": cargo_peso,
            "seguro": seguro,
            "total": cls.FLETE_BASE + cargo_peso + seguro,
        }

    @property
    def desglose_tarifa(self) -> dict[str, Decimal]:
        return self.calcular_tarifa(self.peso_kg, self.valor_declarado)

    @property
    def estados_siguientes(self) -> list[tuple[str, str]]:
        etiquetas = dict(self.ESTADO_CHOICES)
        return [(estado, etiquetas[estado]) for estado in self.TRANSICIONES[self.estado]]

    def cambiar_estado(self, nuevo_estado: str, usuario) -> None:
        """Valida la transicion y guarda solo el estado y quien lo cambio."""
        if nuevo_estado not in self.TRANSICIONES:
            raise ValidationError("Estado no valido.")
        if nuevo_estado not in self.TRANSICIONES[self.estado]:
            raise ValidationError(self._mensaje_transicion(self.estado, nuevo_estado))
        self.estado = nuevo_estado
        self.actualizado_por = usuario
        self.save(update_fields=["estado", "actualizado_por", "updated_at"])


class PagoEncomienda(models.Model):
    encomienda = models.ForeignKey(Encomienda, related_name="pagos", on_delete=models.CASCADE)
    metodo = models.CharField(max_length=20, choices=Pago.METODO_CHOICES)
    monto = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(CENTAVO)]
    )
    referencia_externa = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "pago de encomienda"
        verbose_name_plural = "pagos de encomienda"
        constraints = [
            models.CheckConstraint(
                check=Q(monto__gt=0),
                name="pago_encomienda_monto_positivo",
                violation_error_message="El monto debe ser mayor a 0.",
            ),
        ]

    def __str__(self):
        return f"Pago {self.metodo} — Bs {self.monto} ({self.encomienda.codigo_guia})"

    def clean(self):
        super().clean()
        errores: dict[str, str] = {}

        if self.metodo and self.metodo != "efectivo" and not self.referencia_externa:
            errores["referencia_externa"] = "Este metodo de pago necesita una referencia."

        precio = self.encomienda.precio_envio if self.encomienda_id else None
        if precio is not None and self.monto is not None:
            pagado = (
                self.encomienda.pagos.exclude(pk=self.pk).aggregate(total=Sum("monto"))["total"]
                or Decimal("0")
            )
            if pagado + self.monto > precio:
                errores["monto"] = f"Los pagos superan el precio del envio (Bs {precio})."

        if errores:
            raise ValidationError(errores)


class ComprobanteEncomienda(models.Model):
    encomienda = models.OneToOneField(
        Encomienda, related_name="comprobante", on_delete=models.CASCADE
    )
    numero_comprobante = models.CharField(max_length=30, unique=True, blank=True)
    archivo_pdf = models.FileField(upload_to="comprobantes_encomienda/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "comprobante de encomienda"
        verbose_name_plural = "comprobantes de encomienda"

    def __str__(self):
        return f"{self.numero_comprobante} ({self.encomienda.codigo_guia})"

    def save(self, *args, **kwargs):
        if not self.numero_comprobante:
            self.numero_comprobante = generar_codigo("CME")
        super().save(*args, **kwargs)
