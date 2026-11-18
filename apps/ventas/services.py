"""Logica de ventas que no pertenece a un solo modelo ni a una sola vista.

La usan la venta en ventanilla y, mas adelante, la reserva online."""

from dataclasses import dataclass

from django.contrib.auth import get_user_model

from apps.core.validators import normalizar_ci, validar_ci
from .models import Pasaje


@dataclass(frozen=True)
class PasajeroEncontrado:
    """Datos para precargar el formulario de venta a partir de un CI."""

    nombre: str
    ci: str
    telefono: str
    tiene_cuenta: bool


def cliente_por_ci(ci: str | None):
    """Cuenta activa con ese CI (ya normalizado), o None.

    Se usa al guardar la venta para enlazar Pasaje.cliente en el servidor: asi el
    enlace no depende de un campo oculto que el navegador podria cambiar."""
    if not ci:
        return None
    return get_user_model().objects.filter(ci=ci, is_active=True).first()


def buscar_pasajero_por_ci(ci_texto: str) -> PasajeroEncontrado | None:
    """Busca primero una cuenta con ese CI y, si no hay, la ultima venta con ese CI.

    Lanza ValidationError si el CI no tiene un formato valido."""
    ci = normalizar_ci(ci_texto.strip())
    validar_ci(ci)

    usuario = cliente_por_ci(ci)
    if usuario:
        return PasajeroEncontrado(
            nombre=usuario.get_full_name() or usuario.username,
            ci=ci,
            telefono=usuario.telefono,
            tiene_cuenta=True,
        )

    pasaje = (
        Pasaje.objects.filter(cliente_ci=ci)
        .exclude(cliente_nombre="")
        .order_by("-created_at")
        .first()
    )
    if pasaje:
        return PasajeroEncontrado(
            nombre=pasaje.cliente_nombre, ci=ci, telefono=pasaje.cliente_telefono, tiene_cuenta=False
        )
    return None
