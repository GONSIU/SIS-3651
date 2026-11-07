import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone
from apps.viajes.models import Viaje, AsientoViaje
from apps.core.utils import generar_codigo
from apps.core.validators import (
    normalizar_ci,
    normalizar_espacios,
    validar_ci,
    validar_nombre_persona,
)


class Pasaje(models.Model):
    CANAL_CHOICES = [
        ("ventanilla", "Ventanilla"),
        ("online", "Online"),
    ]
    ESTADO_CHOICES = [
        ("reservado", "Reservado"),
        ("pagado", "Pagado"),
        ("cancelado", "Cancelado"),
        ("reembolsado", "Reembolsado"),
        ("usado", "Usado"),
    ]

    codigo_pasaje = models.CharField(max_length=20, unique=True, blank=True)
    viaje = models.ForeignKey(Viaje, related_name="pasajes", on_delete=models.PROTECT)
    asiento_viaje = models.OneToOneField(
        AsientoViaje, related_name="pasaje", on_delete=models.PROTECT
    )
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pasajes_comprados",
    )
    cliente_nombre = models.CharField(max_length=100, blank=True, validators=[validar_nombre_persona])
    cliente_ci = models.CharField(max_length=12, blank=True, validators=[validar_ci])
    vendido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ventas_realizadas",
    )
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pasajes_actualizados",
    )
    canal = models.CharField(max_length=20, choices=CANAL_CHOICES)
    precio = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="reservado")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=Q(precio__gt=0),
                name="pasaje_precio_positivo",
                violation_error_message="El precio debe ser mayor a 0.",
            ),
            models.CheckConstraint(
                check=Q(cliente__isnull=False) | ~Q(cliente_nombre=""),
                name="pasaje_con_cliente_o_nombre",
                violation_error_message="Indica el cliente o el nombre del pasajero.",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.codigo_pasaje:
            self.codigo_pasaje = generar_codigo("PSJ")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo_pasaje} — {self.viaje}"

    def clean_fields(self, exclude=None):
        self.cliente_nombre = normalizar_espacios(self.cliente_nombre)
        self.cliente_ci = normalizar_ci(self.cliente_ci)
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        errores: dict[str, list[str]] = {}

        if not self.cliente_id and not self.cliente_nombre:
            errores.setdefault("cliente_nombre", []).append("Indica el cliente o el nombre del pasajero.")

        if self.asiento_viaje_id and self.viaje_id and self.asiento_viaje.viaje_id != self.viaje_id:
            errores.setdefault("asiento_viaje", []).append("El asiento no pertenece a este viaje.")

        # Solo al crear: un pasaje ya vendido debe poder editarse aunque el viaje termine.
        if self._state.adding:
            if self.viaje_id:
                if self.viaje.estado in ("cancelado", "completado"):
                    errores.setdefault("viaje", []).append(
                        f"No se puede vender: el viaje esta {self.viaje.get_estado_display().lower()}."
                    )
                elif self.viaje.fecha_salida < timezone.localdate():
                    errores.setdefault("viaje", []).append("No se puede vender: la fecha de salida ya paso.")
            if self.asiento_viaje_id and self.asiento_viaje.estado != "disponible":
                errores.setdefault("asiento_viaje", []).append("Ese asiento ya no esta disponible.")

        if errores:
            raise ValidationError(errores)

    @property
    def nombre_pasajero(self):
        if self.cliente_id:
            return self.cliente.get_full_name() or self.cliente.username
        return self.cliente_nombre or "—"

    def marcar_como_vendido(self):
        """Pasa el asiento asociado a 'vendido' y el pasaje a 'pagado'."""
        self.asiento_viaje.estado = "vendido"
        self.asiento_viaje.save(update_fields=["estado"])
        self.estado = "pagado"
        self.save(update_fields=["estado"])


class Pago(models.Model):
    METODO_CHOICES = [
        ("efectivo", "Efectivo"),
        ("tarjeta", "Tarjeta"),
        ("qr", "QR"),
        ("transferencia", "Transferencia"),
    ]

    pasaje = models.ForeignKey(Pasaje, related_name="pagos", on_delete=models.CASCADE)
    metodo = models.CharField(max_length=20, choices=METODO_CHOICES)
    monto = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    referencia_externa = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=Q(monto__gt=0),
                name="pago_monto_positivo",
                violation_error_message="El monto debe ser mayor a 0.",
            ),
        ]

    def __str__(self):
        return f"Pago {self.metodo} — Bs {self.monto} ({self.pasaje.codigo_pasaje})"

    def clean(self):
        super().clean()
        errores: dict[str, str] = {}

        if self.metodo and self.metodo != "efectivo" and not self.referencia_externa:
            errores["referencia_externa"] = "Este metodo de pago necesita una referencia."

        if self.pasaje_id and self.monto is not None:
            pagado = (
                self.pasaje.pagos.exclude(pk=self.pk).aggregate(total=Sum("monto"))["total"]
                or Decimal("0")
            )
            if pagado + self.monto > self.pasaje.precio:
                errores["monto"] = f"Los pagos superan el precio del pasaje (Bs {self.pasaje.precio})."

        if errores:
            raise ValidationError(errores)


class Comprobante(models.Model):
    TIPO_CHOICES = [
        ("recibo", "Recibo"),
        ("factura", "Factura"),
    ]

    pasaje = models.OneToOneField(Pasaje, related_name="comprobante", on_delete=models.CASCADE)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="recibo")
    numero_comprobante = models.CharField(max_length=30, unique=True, blank=True)
    # Dato fiscal ficticio (no proviene de Impuestos Nacionales): solo para que el
    # boleto impreso se vea como una factura real. Se genera solo, no se captura.
    codigo_control = models.CharField(max_length=40, blank=True)
    archivo_pdf = models.FileField(upload_to="comprobantes/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero_comprobante:
            self.numero_comprobante = generar_codigo("CMP")
        if not self.codigo_control:
            bloques = [uuid.uuid4().hex[:4].upper() for _ in range(4)]
            self.codigo_control = "-".join(bloques)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero_comprobante} ({self.pasaje.codigo_pasaje})"
    