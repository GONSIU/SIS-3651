"""Alertas operativas de la campana del encabezado del personal, calculadas en vivo.

No usan tabla: cada alerta es un COUNT sobre datos que ya existen, igual que los
reportes. Asi nunca queda una alerta vieja que alguien olvido marcar como leida. Cada
alerta enlaza a una vista a la que el rol tiene acceso.

Los avisos del cliente son otra cosa: se guardan en core.models.Notificacion (bandeja
con leida y eliminar), porque cuentan un evento puntual y no un estado actual.

Como core/views.py, este modulo si importa otras apps; core/models.py, mixins.py y
utils.py siguen sin hacerlo.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.db.models import Count, F, Q
from django.urls import reverse
from django.utils import timezone

from apps.encomiendas.models import Encomienda
from apps.incidencias.models import Incidencia
from apps.ventas.models import Pasaje
from apps.ventas.services import PLAZO_REPROGRAMACION
from apps.viajes.models import Viaje

ROLES_VENTANILLA = ("ventanillero", "supervisor", "admin")
ROLES_GESTION = ("supervisor", "admin")
# Un no_show aparece cuando le quedan estos dias (o menos) para reprogramarse.
DIAS_AVISO_REPROGRAMACION = 2
# Un viaje de hoy o manana se considera casi lleno (ruta saturada) con este porcentaje
# de asientos vendidos o reservados.
PORCENTAJE_CASI_LLENO = 90


@dataclass(frozen=True)
class Alerta:
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


def incidencias_pendientes() -> int:
    """Incidencias y reclamos abiertos o en revision."""
    return Incidencia.objects.filter(estado__in=Incidencia.ESTADOS_PENDIENTES).count()


def viajes_casi_llenos(hoy) -> int:
    """Viajes de hoy y manana que aun no salieron con PORCENTAJE_CASI_LLENO % o mas de
    asientos vendidos o reservados (una sola consulta con agregados por viaje)."""
    return (
        Viaje.objects.filter(
            fecha_salida__range=(hoy, hoy + timedelta(days=1)), estado__in=Viaje.ESTADOS_CON_ABORDAJE
        )
        .annotate(
            total=Count("asientos_viaje"),
            ocupados=Count("asientos_viaje", filter=Q(asientos_viaje__estado__in=("vendido", "reservado"))),
        )
        # Enteros: ocupados * 100 >= total * porcentaje (sin division ni decimales).
        .annotate(ocupados_x100=F("ocupados") * 100)
        .filter(total__gt=0, ocupados_x100__gte=F("total") * PORCENTAJE_CASI_LLENO)
        .count()
    )


def notificaciones_para(usuario, ahora: datetime | None = None) -> list[Alerta]:
    """Alertas con cantidad > 0 para el rol del usuario, en orden de urgencia."""
    ahora = ahora or timezone.now()
    hoy = timezone.localtime(ahora).date()
    rol = getattr(usuario, "rol", None)
    candidatas: list[Alerta] = []

    if rol in ROLES_VENTANILLA:
        candidatas += [
            Alerta(
                "schedule", "reserva(s) online vencen hoy sin pagar el saldo",
                reservas_que_vencen_hoy(ahora), reverse("ventas:reservas_pendientes"),
            ),
            Alerta(
                "event_repeat",
                f"pasaje(s) no presentados con plazo de reprogramacion por vencer "
                f"({DIAS_AVISO_REPROGRAMACION} dias o menos)",
                reprogramaciones_por_vencer(ahora), reverse("ventas:reprogramaciones"),
            ),
            Alerta(
                "inventory_2", "encomienda(s) en destino por entregar",
                encomiendas_por_entregar(), f"{reverse('encomiendas:listado')}?estado=en_destino",
            ),
        ]
    if rol in ROLES_GESTION:
        candidatas += [
            Alerta(
                "warning", "viaje(s) retrasados hoy",
                viajes_retrasados_hoy(hoy), reverse("viajes:listado"),
            ),
            Alerta(
                "person_off", "viaje(s) de hoy o manana sin conductor",
                viajes_sin_conductor(hoy), reverse("viajes:listado"),
            ),
            Alerta(
                "groups", f"viaje(s) de hoy o manana casi llenos ({PORCENTAJE_CASI_LLENO} % o mas)",
                viajes_casi_llenos(hoy), reverse("reportes:ocupacion"),
            ),
            Alerta(
                "report", "incidencia(s) o reclamo(s) sin resolver",
                incidencias_pendientes(), reverse("incidencias:listado"),
            ),
        ]
    if rol == "conductor":
        candidatas.append(
            Alerta(
                "directions_bus", "viaje(s) asignados hoy",
                viajes_del_conductor_hoy(usuario, hoy), reverse("viajes:mis_viajes"),
            )
        )
    return [n for n in candidatas if n.cantidad > 0]
