"""Logica de ventas que no pertenece a un solo modelo ni a una sola vista.

La usan la venta en ventanilla y, mas adelante, la reserva online y la confirmacion
de reservas: todas pasan por registrar_venta() y conservan el mismo bloqueo."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_UP, Decimal
import unicodedata

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
# Anticipo minimo de una reserva online: 30 % del precio. No es reembolsable.
PORCENTAJE_ANTICIPO_MINIMO = Decimal("0.30")
# Limites contra reservas abusivas (por cuenta).
MAX_PASAJES_ONLINE_POR_VIAJE = 4
MAX_RESERVAS_PENDIENTES = 6


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
        asiento_viaje = _bloquear_asiento_libre(viaje, asiento_viaje_id)

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

        _registrar_pago(pasaje, pago)
        _emitir_comprobante(pasaje, facturacion)
    return pasaje


def _bloquear_asiento_libre(viaje, asiento_viaje_id: int) -> AsientoViaje:
    """Bloquea el asiento (select_for_update) y exige que siga disponible.

    Debe llamarse dentro de transaction.atomic(): el bloqueo dura hasta el final de la
    transaccion, y es lo que evita que dos personas vendan o reserven el mismo asiento."""
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
    return asiento_viaje


def _registrar_pago(pasaje: Pasaje, pago: DatosPago) -> Pago:
    registro = Pago(pasaje=pasaje, metodo=pago.metodo, monto=pago.monto, referencia_externa=pago.referencia)
    registro.full_clean()
    registro.save()
    return registro


def _emitir_comprobante(pasaje: Pasaje, facturacion: DatosFacturacion) -> Comprobante:
    comprobante = Comprobante(
        pasaje=pasaje,
        tipo="factura" if facturacion.es_factura else "recibo",
        nit_cliente=facturacion.nit,
        razon_social_cliente=facturacion.razon_social,
    )
    comprobante.full_clean()
    comprobante.save()
    return comprobante


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


# --- Reserva online -----------------------------------------------------------


def monto_minimo_anticipo(precio: Decimal) -> Decimal:
    """30 % del precio, redondeado al centavo hacia arriba (nunca menos del 30 %)."""
    return (precio * PORCENTAJE_ANTICIPO_MINIMO).quantize(Decimal("0.01"), rounding=ROUND_UP)


def comparable(nombre: str) -> str:
    """Nombre sin tildes, mayusculas ni espacios de mas, para comparar dos nombres."""
    sin_tildes = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().split())


def validar_nombre_contra_cuenta(nombre: str, ci: str) -> str:
    """Si el CI es de una cuenta con nombre, exige que el nombre escrito coincida y
    devuelve el nombre registrado. Si no, devuelve el nombre escrito.

    El mensaje de error no revela el nombre correcto: asi un cliente no puede averiguar
    a quien pertenece un CI probando numeros."""
    registrado = nombre_registrado(cliente_por_ci(normalizar_ci(ci)))
    if not registrado:
        return nombre
    if comparable(nombre) != comparable(registrado):
        raise ValidationError({"cliente_nombre": "El nombre no coincide con el registrado para ese CI."})
    return registrado


def _comprobar_limites(comprador, viaje) -> None:
    activos_en_viaje = Pasaje.objects.filter(
        cliente=comprador, viaje=viaje, canal="online", estado__in=Pasaje.ESTADOS_ACTIVOS
    ).count()
    if activos_en_viaje >= MAX_PASAJES_ONLINE_POR_VIAJE:
        raise ValidationError(
            f"Ya tienes {MAX_PASAJES_ONLINE_POR_VIAJE} pasajes en este viaje: es el maximo por cuenta."
        )
    pendientes = Pasaje.objects.filter(cliente=comprador, estado="reservado").count()
    if pendientes >= MAX_RESERVAS_PENDIENTES:
        raise ValidationError(
            f"Tienes {MAX_RESERVAS_PENDIENTES} reservas sin pagar por completo. Paga o cancela alguna antes."
        )


def registrar_reserva(
    *,
    viaje,
    asiento_viaje_id: int,
    comprador,
    pasajero: DatosPasajero,
    pago: DatosPago,
    facturacion: DatosFacturacion | None = None,
    ahora: datetime | None = None,
) -> Pasaje:
    """Reserva online con anticipo (30 % a 100 % del precio base).

    - Con el 100 %: el pasaje queda pagado y el asiento vendido.
    - Con menos: reservado hasta CIERRE_RESERVA_ONLINE antes de la salida; el saldo se
      paga en ventanilla. Si no se paga, vence y el anticipo se pierde.

    El comprobante se crea ya (con los datos de facturacion), pero el boleto solo es
    valido para abordar cuando el pasaje esta pagado."""
    facturacion = facturacion or DatosFacturacion()
    ahora = ahora or timezone.now()
    precio = viaje.ruta.precio_base
    if not precio:
        raise ValidationError("Este viaje no se puede reservar por internet.")
    if not viaje_reservable_online(viaje, ahora):
        raise ValidationError("La reserva por internet de este viaje ya cerro. Compra en ventanilla.")
    if pago.monto < monto_minimo_anticipo(precio) or pago.monto > precio:
        raise ValidationError(
            {"monto": f"El pago debe estar entre Bs {monto_minimo_anticipo(precio)} y Bs {precio}."}
        )
    if pago.metodo == "efectivo":
        raise ValidationError({"metodo": "Por internet no se puede pagar en efectivo."})
    nombre = validar_nombre_contra_cuenta(pasajero.nombre, pasajero.ci)

    liberar_reservas_vencidas(viaje=viaje, ahora=ahora)
    pagado_completo = pago.monto == precio

    with transaction.atomic():
        # Bloquear la cuenta serializa las reservas de un mismo cliente: dos pestanas a
        # la vez no pueden pasar los limites contando lo mismo.
        get_user_model().objects.select_for_update().filter(pk=comprador.pk).first()
        _comprobar_limites(comprador, viaje)
        asiento_viaje = _bloquear_asiento_libre(viaje, asiento_viaje_id)

        pasaje = Pasaje(
            viaje=viaje,
            asiento_viaje=asiento_viaje,
            cliente=comprador,
            cliente_nombre=nombre,
            cliente_ci=pasajero.ci,
            cliente_telefono=pasajero.telefono,
            actualizado_por=comprador,
            canal="online",
            precio=precio,
            estado="reservado",
            reservado_hasta=None if pagado_completo else viaje.salida_programada - CIERRE_RESERVA_ONLINE,
        )
        pasaje.full_clean()
        pasaje.save()
        if pagado_completo:
            pasaje.marcar_como_vendido()
        else:
            asiento_viaje.estado = "reservado"
            asiento_viaje.save(update_fields=["estado"])
        _registrar_pago(pasaje, pago)
        _emitir_comprobante(pasaje, facturacion)
    return pasaje


def viaje_reservable_online(viaje, ahora: datetime | None = None) -> bool:
    return viajes_reservables_online(ahora).filter(pk=viaje.pk).exists()


def cancelar_reserva(pasaje: Pasaje, usuario) -> None:
    """El cliente cancela una reserva no pagada por completo. Libera el asiento; el
    anticipo no se devuelve (no hay reembolsos) y queda registrado en sus pagos."""
    with transaction.atomic():
        pasaje = Pasaje.objects.select_for_update().select_related("asiento_viaje").get(pk=pasaje.pk)
        if pasaje.estado != "reservado":
            raise ValidationError("Solo se puede cancelar una reserva pendiente de pago.")
        pasaje.estado = "cancelado"
        pasaje.actualizado_por = usuario
        pasaje.save(update_fields=["estado", "actualizado_por", "updated_at"])
        AsientoViaje.objects.filter(pk=pasaje.asiento_viaje_id, estado="reservado").update(estado="disponible")
