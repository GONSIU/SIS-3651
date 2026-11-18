"""Logica de ventas que no pertenece a un solo modelo ni a una sola vista.

La usan la venta en ventanilla y, mas adelante, la reserva online y la confirmacion
de reservas: todas pasan por registrar_venta() y conservan el mismo bloqueo."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.core.validators import normalizar_ci, validar_ci
from apps.viajes.models import AsientoViaje, Viaje
from .models import Comprobante, Pago, Pasaje


# La reserva online cierra este tiempo antes de la salida: despues solo se vende en
# ventanilla. Es tambien el plazo para pagar el saldo de una reserva.
CIERRE_RESERVA_ONLINE = timedelta(hours=1)


@dataclass(frozen=True)
class DatosPasajero:
    """Quien viaja (puede no ser la cuenta que compra)."""

    nombre: str
    ci: str = ""
    telefono: str = ""


@dataclass(frozen=True)
class DatosPago:
    metodo: str
    monto: Decimal
    referencia: str = ""


@dataclass(frozen=True)
class DatosFacturacion:
    """Vacio: recibo. Con NIT o CI y razon social: factura."""

    nit: str = ""
    razon_social: str = ""

    @property
    def es_factura(self) -> bool:
        return bool(self.nit)


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


def nombre_registrado(cliente) -> str:
    """Nombre completo de la cuenta, o "" si la cuenta no lo tiene."""
    return cliente.get_full_name() if cliente else ""


def registrar_venta(
    *,
    viaje,
    asiento_viaje_id: int,
    pasajero: DatosPasajero,
    precio: Decimal,
    pago: DatosPago,
    vendido_por,
    canal: str = "ventanilla",
    facturacion: DatosFacturacion | None = None,
) -> Pasaje:
    """Vende un asiento pagado por completo: pasaje, pago y comprobante.

    Todo ocurre en una transaccion y con el AsientoViaje bloqueado
    (select_for_update): si dos personas venden el mismo asiento a la vez, la segunda
    espera, ve el asiento ya vendido y recibe ValidationError. Cualquier error deshace
    todo lo guardado. Es el unico lugar que debe crear ventas."""
    facturacion = facturacion or DatosFacturacion()
    liberar_reservas_vencidas(viaje=viaje)

    with transaction.atomic():
        asiento_viaje = (
            AsientoViaje.objects.select_for_update()
            .select_related("asiento")
            .filter(pk=asiento_viaje_id, viaje=viaje)
            .first()
        )
        if asiento_viaje is None:
            raise ValidationError("Ese asiento no pertenece al viaje elegido.")
        if asiento_viaje.estado != "disponible":
            raise ValidationError("Ese asiento ya no esta disponible. Elige otro.")

        # El enlace con la cuenta y el nombre se deciden aqui, no en el formulario: si el
        # CI es de una cuenta con nombre, el boleto lleva ese nombre aunque se haya
        # escrito otro.
        cliente = cliente_por_ci(normalizar_ci(pasajero.ci))
        pasaje = Pasaje(
            viaje=viaje,
            asiento_viaje=asiento_viaje,
            cliente=cliente,
            cliente_nombre=nombre_registrado(cliente) or pasajero.nombre,
            cliente_ci=pasajero.ci,
            cliente_telefono=pasajero.telefono,
            vendido_por=vendido_por,
            actualizado_por=vendido_por,
            canal=canal,
            precio=precio,
        )
        pasaje.full_clean()
        pasaje.save()
        pasaje.marcar_como_vendido()

        registro_pago = Pago(
            pasaje=pasaje, metodo=pago.metodo, monto=pago.monto, referencia_externa=pago.referencia
        )
        registro_pago.full_clean()
        registro_pago.save()

        comprobante = Comprobante(
            pasaje=pasaje,
            tipo="factura" if facturacion.es_factura else "recibo",
            nit_cliente=facturacion.nit,
            razon_social_cliente=facturacion.razon_social,
        )
        comprobante.full_clean()
        comprobante.save()
    return pasaje


def liberar_reservas_vencidas(viaje=None, ahora: datetime | None = None) -> int:
    """Pasa a "vencido" las reservas cuyo reservado_hasta ya paso y libera su asiento.

    Se llama antes de mostrar asientos o de vender (vencimiento "perezoso": no hace
    falta un proceso en segundo plano). skip_locked=True salta las reservas que otra
    transaccion tiene bloqueadas, por ejemplo una que se esta cobrando en ese momento.
    Devuelve cuantas reservas vencio."""
    ahora = ahora or timezone.now()
    with transaction.atomic():
        vencidas = Pasaje.objects.select_for_update(skip_locked=True).filter(
            estado="reservado", reservado_hasta__lt=ahora
        )
        if viaje is not None:
            vencidas = vencidas.filter(viaje=viaje)
        ids = list(vencidas.values_list("pk", flat=True))
        if not ids:
            return 0
        # update() no pasa por save(): updated_at se pone a mano.
        AsientoViaje.objects.filter(pasajes__pk__in=ids, estado="reservado").update(estado="disponible")
        Pasaje.objects.filter(pk__in=ids).update(estado="vencido", updated_at=ahora)
    return len(ids)


def con_conteo_de_asientos(viajes):
    """Anota num_asientos y num_libres en la misma consulta (sin un count() por viaje)."""
    return viajes.annotate(
        num_asientos=Count("asientos_viaje"),
        num_libres=Count("asientos_viaje", filter=Q(asientos_viaje__estado="disponible")),
    )


def viajes_reservables_online(ahora: datetime | None = None):
    """Viajes que se pueden reservar por internet ahora.

    Vendibles (no salieron, no terminaron, no cancelados), con precio_base (el cliente no
    escribe el precio) y con salida despues de ahora + CIERRE_RESERVA_ONLINE. El limite
    se compara como fecha y hora por separado para que funcione cerca de medianoche."""
    limite = timezone.localtime(ahora or timezone.now()) + CIERRE_RESERVA_ONLINE
    viajes = (
        Viaje.objects.exclude(estado__in=Viaje.ESTADOS_SIN_VENTA)
        .filter(ruta__precio_base__isnull=False)
        .filter(
            Q(fecha_salida__gt=limite.date())
            | Q(fecha_salida=limite.date(), horario__hora_salida__gt=limite.time())
        )
        .select_related("ruta__origen", "ruta__destino", "bus", "horario")
        .order_by("fecha_salida", "horario__hora_salida")
    )
    return con_conteo_de_asientos(viajes)


def agrupar_asientos(asientos_viaje) -> list[tuple[int, list[list]]]:
    """Arma [(piso, [[col1, col2, col3, col4], ...]), ...] para dibujar el mapa
    2 + pasillo + 2 en la plantilla sin logica compleja ahi. Una celda vacia es None."""
    pisos = defaultdict(lambda: defaultdict(dict))
    for av in asientos_viaje:
        pisos[av.asiento.piso or 1][av.asiento.fila or 0][av.asiento.columna or 0] = av

    resultado = []
    for piso in sorted(pisos):
        filas = [
            [pisos[piso][fila].get(columna) for columna in (1, 2, 3, 4)]
            for fila in sorted(pisos[piso])
        ]
        resultado.append((piso, filas))
    return resultado


def mapa_de_asientos(viaje) -> list[tuple[int, list[list]]]:
    """Mapa del viaje listo para la plantilla ventas/_mapa_asientos.html."""
    asientos = viaje.asientos_viaje.select_related("asiento").order_by(
        "asiento__piso", "asiento__fila", "asiento__columna"
    )
    return agrupar_asientos(asientos)
