"""Consultas de agregacion de los reportes (REQF5). No hay modelos propios: todo se
calcula en vivo sobre Pasaje, Pago, Viaje, AsientoViaje y Encomienda.

Reglas (docs/reportes.md):
- Pasaje vendido: estado en PASAJE_ESTADOS_VENDIDOS, por fecha de venta (created_at).
- Ingresos de pasajes: dinero cobrado, suma de Pago.monto por fecha de cobro.
- Encomiendas: por fecha de registro; ingreso = precio_envio (se cobra al registrar).
- Terminal: terminal de origen de la ruta del viaje.
- Ocupacion: AsientoViaje vendidos / AsientoViaje del viaje; sin viajes cancelados.
"""
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate

from apps.encomiendas.models import Encomienda
from apps.ventas.models import Pago, Pasaje
from apps.viajes.models import Viaje

TIPOS_PERIODO = ("diario", "semanal", "mensual")
MAX_DIAS_PERIODO = 366
PASAJE_ESTADOS_VENDIDOS = ("pagado", "usado", "no_show", "reprogramado")
MAX_RUTAS_GRAFICO = 8
CERO = Decimal("0")


# --- Periodos ----------------------------------------------------------------


@dataclass(frozen=True)
class Periodo:
    desde: date
    hasta: date
    tipo: str  # diario, semanal, mensual o personalizado

    @property
    def dias(self) -> int:
        return (self.hasta - self.desde).days + 1

    def fechas(self) -> list[date]:
        """Dias del periodo, del mas reciente al mas antiguo (orden de la tabla)."""
        return [self.hasta - timedelta(days=i) for i in range(self.dias)]

    def anterior(self) -> "Periodo":
        """Periodo equivalente anterior, para comparar.

        - diario: ayer.
        - semanal: los 7 dias anteriores.
        - mensual (mes en curso hasta hoy): el mismo tramo del mes anterior, del dia 1
          al mismo dia (o al ultimo, si el mes anterior es mas corto). Comparar 18 dias
          contra un mes completo seria injusto.
        - personalizado: el mismo numero de dias justo antes."""
        if self.tipo == "mensual":
            fin_mes_anterior = self.desde - timedelta(days=1)
            inicio = fin_mes_anterior.replace(day=1)
            ultimo_dia = monthrange(inicio.year, inicio.month)[1]
            return Periodo(inicio, inicio.replace(day=min(self.hasta.day, ultimo_dia)), self.tipo)
        return Periodo(self.desde - timedelta(days=self.dias), self.desde - timedelta(days=1), self.tipo)

    @property
    def etiqueta_comparacion(self) -> str:
        return {
            "diario": "vs ayer",
            "semanal": "vs 7 dias anteriores",
            "mensual": "vs mismo tramo del mes anterior",
        }.get(self.tipo, "vs periodo anterior")


def periodo_predefinido(tipo: str, hoy: date) -> Periodo:
    if tipo == "diario":
        return Periodo(hoy, hoy, tipo)
    if tipo == "semanal":
        return Periodo(hoy - timedelta(days=6), hoy, tipo)
    return Periodo(hoy.replace(day=1), hoy, "mensual")


def porcentaje(parte, total) -> float | None:
    """parte / total * 100, o None si total es 0 (no se puede calcular)."""
    return float(parte) / float(total) * 100 if total else None


def variacion_pct(actual, anterior) -> float | None:
    """Variacion porcentual contra el periodo anterior; None si no hay base para comparar."""
    return (float(actual) - float(anterior)) / float(anterior) * 100 if anterior else None


# --- Filtros -------------------------------------------------------------------


def _filtro_ruta(prefijo: str, ruta=None, terminal=None) -> Q:
    """Q por ruta y terminal de origen; prefijo es el camino hasta el viaje."""
    q = Q()
    if ruta is not None:
        q &= Q(**{f"{prefijo}ruta": ruta})
    if terminal is not None:
        q &= Q(**{f"{prefijo}ruta__origen": terminal})
    return q


def _pasajes_vendidos(periodo: Periodo, ruta=None, terminal=None):
    return Pasaje.objects.filter(
        _filtro_ruta("viaje__", ruta, terminal),
        estado__in=PASAJE_ESTADOS_VENDIDOS,
        created_at__date__range=(periodo.desde, periodo.hasta),
    )


def _pagos(periodo: Periodo, ruta=None, terminal=None):
    return Pago.objects.filter(
        _filtro_ruta("pasaje__viaje__", ruta, terminal),
        created_at__date__range=(periodo.desde, periodo.hasta),
    )


def _encomiendas(periodo: Periodo, ruta=None, terminal=None):
    return Encomienda.objects.filter(
        _filtro_ruta("viaje__", ruta, terminal),
        created_at__date__range=(periodo.desde, periodo.hasta),
    )


def _por_dia(queryset, valor) -> dict[date, object]:
    """{fecha: agregado} agrupando por la fecha local de created_at."""
    filas = queryset.annotate(dia=TruncDate("created_at")).values("dia").annotate(valor=valor).order_by()
    return {fila["dia"]: fila["valor"] for fila in filas}


# --- Reporte de ventas ---------------------------------------------------------------


@dataclass
class VentaRuta:
    ruta: str
    total: Decimal
    ancho_pct: float  # largo de la barra respecto de la ruta con mas ingresos


@dataclass
class FilaDiaria:
    fecha: date
    pasajes: int
    encomiendas: int
    ingresos: Decimal


@dataclass
class ReporteVentas:
    periodo: Periodo
    pasajes_vendidos: int
    ingresos_pasajes: Decimal
    encomiendas: int
    ingresos_encomiendas: Decimal
    variacion_pasajes_pct: float | None
    rutas: list[VentaRuta] = field(default_factory=list)
    total_rutas: int = 0
    filas: list[FilaDiaria] = field(default_factory=list)

    @property
    def ingresos_totales(self) -> Decimal:
        return self.ingresos_pasajes + self.ingresos_encomiendas

    @property
    def variacion_texto(self) -> str:
        """"+12% vs ayer"; vacio si no hay periodo anterior con ventas para comparar."""
        if self.variacion_pasajes_pct is None:
            return ""
        return f"{self.variacion_pasajes_pct:+.0f}% {self.periodo.etiqueta_comparacion}"

    @property
    def hay_movimiento(self) -> bool:
        return bool(self.pasajes_vendidos or self.encomiendas or self.ingresos_totales)


def reporte_ventas(periodo: Periodo, ruta=None, terminal=None) -> ReporteVentas:
    pasajes = _pasajes_vendidos(periodo, ruta, terminal)
    pagos = _pagos(periodo, ruta, terminal)
    encomiendas = _encomiendas(periodo, ruta, terminal)

    pasajes_vendidos = pasajes.count()
    ingresos_pasajes = pagos.aggregate(total=Sum("monto"))["total"] or CERO
    totales_encomiendas = encomiendas.aggregate(cantidad=Count("id"), total=Sum("precio_envio"))
    anteriores = _pasajes_vendidos(periodo.anterior(), ruta, terminal).count()

    # Ingresos por ruta: una consulta agrupada; los nombres salen de values() (sin N+1).
    por_ruta = list(
        pagos.values(
            "pasaje__viaje__ruta",
            "pasaje__viaje__ruta__origen__ciudad",
            "pasaje__viaje__ruta__destino__ciudad",
        )
        .annotate(total=Sum("monto"))
        .order_by("-total", "pasaje__viaje__ruta__origen__ciudad")
    )
    maximo = por_ruta[0]["total"] if por_ruta else CERO
    rutas = [
        VentaRuta(
            ruta=f"{fila['pasaje__viaje__ruta__origen__ciudad']} → {fila['pasaje__viaje__ruta__destino__ciudad']}",
            total=fila["total"],
            ancho_pct=porcentaje(fila["total"], maximo) or 0,
        )
        for fila in por_ruta[:MAX_RUTAS_GRAFICO]
    ]

    pasajes_dia = _por_dia(pasajes, Count("id"))
    pagos_dia = _por_dia(pagos, Sum("monto"))
    encomiendas_dia = _por_dia(encomiendas, Count("id"))
    ingresos_encomiendas_dia = _por_dia(encomiendas, Sum("precio_envio"))
    filas = [
        FilaDiaria(
            fecha=dia,
            pasajes=pasajes_dia.get(dia, 0),
            encomiendas=encomiendas_dia.get(dia, 0),
            ingresos=(pagos_dia.get(dia) or CERO) + (ingresos_encomiendas_dia.get(dia) or CERO),
        )
        for dia in periodo.fechas()
    ]

    return ReporteVentas(
        periodo=periodo,
        pasajes_vendidos=pasajes_vendidos,
        ingresos_pasajes=ingresos_pasajes,
        encomiendas=totales_encomiendas["cantidad"],
        ingresos_encomiendas=totales_encomiendas["total"] or CERO,
        variacion_pasajes_pct=variacion_pct(pasajes_vendidos, anteriores),
        rutas=rutas,
        total_rutas=len(por_ruta),
        filas=filas,
    )


# --- Reporte de ocupacion ------------------------------------------------------------


@dataclass
class ReporteOcupacion:
    viajes: list[Viaje]
    capacidad: int
    vendidos: int
    reservados: int

    @property
    def ocupacion_pct(self) -> float | None:
        return porcentaje(self.vendidos, self.capacidad)


def reporte_ocupacion(periodo: Periodo, ruta=None, terminal=None) -> ReporteOcupacion:
    """Viajes no cancelados con salida en el periodo, con asientos totales, vendidos y
    reservados contados en la misma consulta (Count con filter)."""
    viajes = list(
        Viaje.objects.filter(
            _filtro_ruta("", ruta, terminal),
            fecha_salida__range=(periodo.desde, periodo.hasta),
        )
        .exclude(estado="cancelado")
        .select_related("ruta__origen", "ruta__destino", "bus", "horario")
        .annotate(
            capacidad=Count("asientos_viaje"),
            vendidos=Count("asientos_viaje", filter=Q(asientos_viaje__estado="vendido")),
            reservados=Count("asientos_viaje", filter=Q(asientos_viaje__estado="reservado")),
        )
        .order_by("fecha_salida", "horario__hora_salida")
    )
    for viaje in viajes:
        viaje.ocupacion_pct = porcentaje(viaje.vendidos, viaje.capacidad)
    return ReporteOcupacion(
        viajes=viajes,
        capacidad=sum(v.capacidad for v in viajes),
        vendidos=sum(v.vendidos for v in viajes),
        reservados=sum(v.reservados for v in viajes),
    )


# --- Reporte de encomiendas ----------------------------------------------------------


@dataclass
class EstadoEncomiendas:
    estado: str
    etiqueta: str
    cantidad: int
    pct: float | None


@dataclass
class ReporteEncomiendas:
    estados: list[EstadoEncomiendas]
    total: int
    despachadas: int  # solo "entregado", el mismo criterio del dashboard

    @property
    def despachadas_pct(self) -> float | None:
        return porcentaje(self.despachadas, self.total)


def reporte_encomiendas(periodo: Periodo, ruta=None, terminal=None) -> ReporteEncomiendas:
    conteo = dict(
        _encomiendas(periodo, ruta, terminal)
        .values("estado")
        .annotate(cantidad=Count("id"))
        .order_by()
        .values_list("estado", "cantidad")
    )
    total = sum(conteo.values())
    # Todos los estados, aunque tengan 0, en el orden del modelo.
    estados = [
        EstadoEncomiendas(estado, etiqueta, conteo.get(estado, 0), porcentaje(conteo.get(estado, 0), total))
        for estado, etiqueta in Encomienda.ESTADO_CHOICES
    ]
    return ReporteEncomiendas(estados=estados, total=total, despachadas=conteo.get("entregado", 0))
