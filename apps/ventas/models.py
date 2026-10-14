from django.conf import settings
from django.db import models
from apps.viajes.models import Viaje, AsientoViaje
from apps.core.utils import generar_codigo


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
    cliente_nombre = models.CharField(max_length=150, blank=True)
    cliente_ci = models.CharField(max_length=20, blank=True)
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
    precio = models.DecimalField(max_digits=8, decimal_places=2)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="reservado")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.codigo_pasaje:
            self.codigo_pasaje = generar_codigo("PSJ")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo_pasaje} — {self.viaje}"

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
    monto = models.DecimalField(max_digits=8, decimal_places=2)
    referencia_externa = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Pago {self.metodo} — Bs {self.monto} ({self.pasaje.codigo_pasaje})"


class Comprobante(models.Model):
    TIPO_CHOICES = [
        ("recibo", "Recibo"),
        ("factura", "Factura"),
    ]

    pasaje = models.OneToOneField(Pasaje, related_name="comprobante", on_delete=models.CASCADE)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="recibo")
    numero_comprobante = models.CharField(max_length=30, unique=True, blank=True)
    archivo_pdf = models.FileField(upload_to="comprobantes/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.numero_comprobante:
            self.numero_comprobante = generar_codigo("CMP")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero_comprobante} ({self.pasaje.codigo_pasaje})"
