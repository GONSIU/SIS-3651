"""Alertas operativas de la campana del encabezado, calculadas en vivo.

No hay tabla de notificaciones: cada alerta es un COUNT sobre datos que ya existen, igual
que los reportes. Asi nunca queda una alerta vieja que alguien olvido marcar como leida.
Cada alerta enlaza a una vista a la que el rol tiene acceso.

Como core/views.py, este modulo si importa otras apps; core/models.py, mixins.py y
utils.py siguen sin hacerlo.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.urls import reverse
from django.utils import timezone

from apps.encomiendas.models import Encomienda
from apps.ventas.models import Pasaje
from apps.ventas.services import PLAZO_REPROGRAMACION
from apps.viajes.models import Viaje

ROLES_VENTANILLA = ("ventanillero", "supervisor", "admin")
ROLES_GESTION = ("supervisor", "admin")
# Un no_show aparece cuando le quedan estos dias (o menos) para reprogramarse.
DIAS_AVISO_REPROGRAMACION = 2


@dataclass(frozen=True)
class Notificacion:
    icono: str  # nombre de Material Symbols
    texto: str
    cantidad: int
    url: str


def _fin_del_dia(ahora: datetime) -> datetime:
    manana = timezone.localtime(ahora).date() + timedelta(days=1)
    return timezone.make_aware(datetime.combine(manana, time.min))


def reservas_que_vencen_hoy(ahora: datetime) -> int:
    """Reservas online vigentes cuyo plazo para pagar el saldo termina hoy.

    No llama a services.reservas_pendientes(): esa funcion libera reservas vencidas (una
    escritura) y aqui se calcula en cada pagina."""
    return Pasaje.objects.filter(
        estado="reservado", reservado_hasta__gt=ahora, reservado_hasta__lt=_fin_del_dia(ahora)
    ).count()


def reprogramaciones_por_vencer(ahora: datetime) -> int:
    """no_show reprogramables cuyo plazo vence en los proximos DIAS_AVISO dias.

    Como services.pasajes_reprogramables(), filtra por dia de salida (aproximado);
    motivo_no_reprogramable() hace el chequeo exacto al reprogramar."""
    hoy = timezone.localtime(ahora).date()
    vence_desde = hoy - PLAZO_REPROGRAMACION
    vence_hasta = vence_desde + timedelta(days=DIAS_AVISO_REPROGRAMACION)
    return Pasaje.objects.filter(
        estado="no_show",
        reprogramado_de__isnull=True,
        viaje__fecha_salida__gte=vence_desde,
        viaje__fecha_salida__lte=vence_hasta,
    ).count()


def encomiendas_por_entregar() -> int:
    return Encomienda.objects.filter(estado="en_destino").count()


def viajes_retrasados_hoy(hoy) -> int:
    return Viaje.objects.filter(fecha_salida=hoy, estado="retrasado").count()


def viajes_sin_conductor(hoy) -> int:
    """Viajes de hoy y manana que todavia no tienen conductor y aun no salieron."""
    return Viaje.objects.filter(
        fecha_salida__range=(hoy, hoy + timedelta(days=1)),
        estado__in=Viaje.ESTADOS_CON_ABORDAJE,
        conductor__isnull=True,
    ).count()


def viajes_del_conductor_hoy(usuario, hoy) -> int:
    return Viaje.objects.filter(
        conductor__usuario=usuario, fecha_salida=hoy, estado__in=Viaje.ESTADOS_CON_ABORDAJE
    ).count()


def notificaciones_para(usuario, ahora: datetime | None = None) -> list[Notificacion]:
    """Alertas con cantidad > 0 para el rol del usuario, en orden de urgencia."""
    ahora = ahora or timezone.now()
    hoy = timezone.localtime(ahora).date()
    rol = getattr(usuario, "rol", None)
    candidatas: list[Notificacion] = []

    if rol in ROLES_VENTANILLA:
        candidatas += [
            Notificacion(
                "schedule", "reserva(s) online vencen hoy sin pagar el saldo",
                reservas_que_vencen_hoy(ahora), reverse("ventas:reservas_pendientes"),
            ),
            Notificacion(
                "event_repeat",
                f"pasaje(s) no presentados con plazo de reprogramacion por vencer "
                f"({DIAS_AVISO_REPROGRAMACION} dias o menos)",
                reprogramaciones_por_vencer(ahora), reverse("ventas:reprogramaciones"),
            ),
            Notificacion(
                "inventory_2", "encomienda(s) en destino por entregar",
                encomiendas_por_entregar(), f"{reverse('encomiendas:listado')}?estado=en_destino",
            ),
        ]
    if rol in ROLES_GESTION:
        candidatas += [
            Notificacion(
                "warning", "viaje(s) retrasados hoy",
                viajes_retrasados_hoy(hoy), reverse("viajes:listado"),
            ),
            Notificacion(
                "person_off", "viaje(s) de hoy o manana sin conductor",
                viajes_sin_conductor(hoy), reverse("viajes:listado"),
            ),
        ]
    if rol == "conductor":
        candidatas.append(
            Notificacion(
                "directions_bus", "viaje(s) asignados hoy",
                viajes_del_conductor_hoy(usuario, hoy), reverse("viajes:mis_viajes"),
            )
        )
    return [n for n in candidatas if n.cantidad > 0]
