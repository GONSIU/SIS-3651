# Vistas de la app "core"
from dataclasses import dataclass, field
from datetime import time

from django.db.models import Prefetch
from django.utils import timezone
from django.utils.text import slugify
from django.views.generic import TemplateView

from apps.core.mixins import RolRequeridoMixin
from apps.rutas.models import Horario, Ruta
from apps.viajes.models import Viaje
from apps.ventas.models import Pasaje
from apps.encomiendas.models import Encomienda

class LandingView(TemplateView):
    """Pagina de inicio publica en "/": barra y hero con el boton de compra. La abre
    cualquiera, con o sin sesion (esta en VISTAS_PUBLICAS del middleware)."""

    template_name = "core/landing.html"


# Fotos en static/img/ciudades/<slug>.jpg (creditos en salidas.html). Los alias cubren
# terminales cargados con el nombre del departamento en vez del de la ciudad.
IMAGENES_CIUDADES = frozenset({"la-paz", "cochabamba", "santa-cruz", "sucre", "potosi", "oruro"})
ALIAS_IMAGEN_CIUDAD = {"chuquisaca": "sucre", "santa-cruz-de-la-sierra": "santa-cruz"}


@dataclass
class DestinoSalidas:
    ciudad: str
    horas: list[time] = field(default_factory=list)


@dataclass
class OrigenSalidas:
    ciudad: str
    destinos: list[DestinoSalidas] = field(default_factory=list)

    @property
    def imagen(self) -> str | None:
        """Ruta relativa a static/ de la foto de la ciudad, o None si no hay."""
        slug = slugify(self.ciudad)
        slug = ALIAS_IMAGEN_CIUDAD.get(slug, slug)
        return f"img/ciudades/{slug}.jpg" if slug in IMAGENES_CIUDADES else None


def salidas_por_origen() -> list[OrigenSalidas]:
    """Rutas activas agrupadas por ciudad de origen y, dentro, por ciudad de destino,
    con las horas de sus horarios activos (sin repetir y en orden).

    Se agrupa por el texto exacto de Terminal.ciudad, el mismo que usa el filtro de
    BuscarViajeForm: asi el boton "Comprar" llega con el origen preseleccionado. Dos
    terminales de la misma ciudad suman sus destinos y horarios. Un destino sin
    horarios activos se lista igual, con la lista de horas vacia."""
    rutas = (
        Ruta.objects.filter(activa=True)
        .select_related("origen", "destino")
        .prefetch_related(
            Prefetch("horarios", queryset=Horario.objects.filter(activo=True).order_by("hora_salida"))
        )
        .order_by("origen__ciudad", "destino__ciudad")
    )
    origenes: dict[str, dict[str, set[time]]] = {}
    for ruta in rutas:
        destinos = origenes.setdefault(ruta.origen.ciudad, {})
        horas = destinos.setdefault(ruta.destino.ciudad, set())
        horas.update(h.hora_salida for h in ruta.horarios.all())
    return [
        OrigenSalidas(
            ciudad=origen,
            destinos=[DestinoSalidas(ciudad=d, horas=sorted(h)) for d, h in destinos.items()],
        )
        for origen, destinos in origenes.items()
    ]


class SalidasView(TemplateView):
    """Catalogo publico de salidas: una tarjeta por ciudad de origen con sus destinos y
    un modal con las horas por destino. Las fechas concretas y los asientos se
    consultan en ventas:buscar_viajes."""

    template_name = "core/salidas.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["origenes"] = salidas_por_origen()
        return context


class NosotrosView(TemplateView):
    """Historia, mision y vision de la empresa. Publica y estatica."""

    template_name = "core/nosotros.html"


class IndexView(RolRequeridoMixin, TemplateView):
    roles_permitidos = ["ventanillero", "supervisor", "admin"]
    template_name = "core/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoy = timezone.localdate()

        pasajes_hoy = Pasaje.objects.filter(created_at__date=hoy)
        rutas_totales = Ruta.objects.count()
        rutas_activas = Ruta.objects.filter(activa=True).count()

        proximas_salidas = (
            Viaje.objects.filter(fecha_salida=hoy)
            .select_related("ruta__origen", "ruta__destino", "bus", "horario")
            .order_by("horario__hora_salida")[:5]
        )
        for viaje in proximas_salidas:
            total_asientos = viaje.asientos_viaje.count()
            vendidos = viaje.asientos_viaje.filter(estado="vendido").count()
            viaje.ocupacion_texto = f"{vendidos}/{total_asientos}" if total_asientos else "—"
            viaje.ocupacion_pct = int(vendidos / total_asientos * 100) if total_asientos else 0

        ventas_recientes = (
            Pasaje.objects.select_related("viaje__ruta__origen", "viaje__ruta__destino")
            .order_by("-created_at")[:5]
        )

        encomiendas_total = Encomienda.objects.count()
        encomiendas_despachadas = Encomienda.objects.filter(estado="entregado").count()
        encomiendas_despachadas_pct = (
            int(encomiendas_despachadas / encomiendas_total * 100) if encomiendas_total else 0
        )

        context.update(
            {
                "boletos_hoy": pasajes_hoy.count(),
                "rutas_activas": rutas_activas,
                "rutas_totales": rutas_totales,
                "rutas_activas_pct": int(rutas_activas / rutas_totales * 100) if rutas_totales else 0,
                "proximas_salidas": proximas_salidas,
                "ventas_recientes": ventas_recientes,
                "encomiendas_total": encomiendas_total,
                "encomiendas_despachadas_pct": encomiendas_despachadas_pct,
            }
        )
        return context
