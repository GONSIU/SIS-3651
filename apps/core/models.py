from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Modelo base abstracto con auditoría de creación/actualización."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True


class Notificacion(models.Model):
    """Aviso guardado para un usuario (bandeja del cliente).

    Distinto de la campana del personal (core/notificaciones.py), que calcula alertas en
    vivo y no guarda nada. Aqui cada aviso es una fila: se puede leer, marcar como leido
    y eliminar. Se crea con Notificacion.avisar() desde los servicios y metodos de modelo
    que producen el evento (reserva, cobro, retraso, reclamo...)."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="notificaciones", on_delete=models.CASCADE
    )
    titulo = models.CharField(max_length=120)
    mensaje = models.TextField(max_length=1000)
    # Ruta interna a la que lleva el aviso (p. ej. el boleto). Vacia si no lleva a ningun lado.
    url = models.CharField(max_length=200, blank=True)
    leida = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "notificacion"
        verbose_name_plural = "notificaciones"
        indexes = [models.Index(fields=["usuario", "leida"], name="notif_usuario_leida_idx")]

    def __str__(self):
        return f"{self.titulo} ({self.usuario})"

    @classmethod
    def avisar(cls, usuarios_ids, titulo: str, mensaje: str, url: str = "") -> int:
        """Crea el mismo aviso para cada usuario (ids o un solo id). Ignora None y
        repetidos. Devuelve cuantos avisos creo."""
        if isinstance(usuarios_ids, int):
            usuarios_ids = [usuarios_ids]
        ids = {pk for pk in usuarios_ids if pk is not None}
        cls.objects.bulk_create(
            [cls(usuario_id=pk, titulo=titulo, mensaje=mensaje, url=url) for pk in sorted(ids)]
        )
        return len(ids)

    def marcar_leida(self) -> None:
        if not self.leida:
            self.leida = True
            self.save(update_fields=["leida"])
