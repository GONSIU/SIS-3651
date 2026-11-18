from decimal import Decimal

from django.contrib import messages
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView

from apps.core.mixins import RolRequeridoMixin
from .models import Viaje
from .forms import ViajeForm


class ListaViajesView(RolRequeridoMixin, ListView):
    roles_permitidos = ["supervisor", "admin"]
    model = Viaje
    template_name = "viajes/listado.html"
    context_object_name = "viajes"

    def get_queryset(self):
        return (
            Viaje.objects.select_related(
                "ruta__origen", "ruta__destino", "bus", "horario", "conductor__usuario"
            )
            .order_by("-fecha_salida", "horario__hora_salida")[:50]
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for viaje in context["viajes"]:
            total = viaje.asientos_viaje.count()
            vendidos = viaje.asientos_viaje.filter(estado="vendido").count()
            viaje.ocupacion_texto = f"{vendidos}/{total}" if total else "—"
        return context


class NuevoViajeView(RolRequeridoMixin, CreateView):
    roles_permitidos = ["supervisor", "admin"]
    model = Viaje
    form_class = ViajeForm
    template_name = "viajes/nuevo.html"
    success_url = reverse_lazy("viajes:listado")

    def form_valid(self, form):
        form.instance.creado_por = self.request.user
        form.instance.actualizado_por = self.request.user
        response = super().form_valid(form)
        self.object.crear_asientos_desde_bus()
        messages.success(
            self.request,
            f"Viaje programado para el {self.object.fecha_salida} con "
            f"{self.object.asientos_viaje.count()} asientos disponibles.",
        )
        return response
    

class MisViajesView(RolRequeridoMixin, ListView):
    """Viajes asignados al conductor que inicio sesion. ?historial=1 muestra los pasados."""

    roles_permitidos = ["conductor"]
    template_name = "viajes/mis_viajes.html"
    context_object_name = "viajes"

    @property
    def es_historial(self) -> bool:
        return self.request.GET.get("historial") == "1"

    def get_queryset(self):
        hoy = timezone.localdate()
        viajes = Viaje.objects.filter(conductor__usuario=self.request.user).select_related(
            "ruta__origen", "ruta__destino", "bus", "horario"
        )
        if self.es_historial:
            return viajes.filter(fecha_salida__lt=hoy).order_by("-fecha_salida", "-horario__hora_salida")
        return viajes.filter(fecha_salida__gte=hoy).order_by("fecha_salida", "horario__hora_salida")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["es_historial"] = self.es_historial
        return context


def _orden_asiento(pasaje) -> tuple:
    """Ordena por numero de asiento como numero ("2" antes que "10"), no como texto."""
    numero = pasaje.asiento_viaje.asiento.numero
    return (0, int(numero), "") if numero.isdigit() else (1, 0, numero)


class HojaRutaView(RolRequeridoMixin, DetailView):
    """Hoja de ruta imprimible: datos del viaje, pasajeros por asiento y encomiendas.

    El conductor solo ve sus viajes: uno ajeno da 404 (no 403) para no revelar que existe."""

    roles_permitidos = ["conductor", "supervisor", "admin"]
    template_name = "viajes/hoja_ruta.html"
    context_object_name = "viaje"
    # Pasajes que viajan; los cancelados ya no ocupan el asiento.
    ESTADOS_PASAJE_A_BORDO = ("reservado", "pagado", "usado")

    def get_queryset(self):
        viajes = Viaje.objects.select_related(
            "ruta__origen", "ruta__destino", "bus", "horario", "conductor__usuario"
        )
        if self.request.user.rol == "conductor":
            viajes = viajes.filter(conductor__usuario=self.request.user)
        return viajes

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pasajes = sorted(
            self.object.pasajes.filter(estado__in=self.ESTADOS_PASAJE_A_BORDO).select_related(
                "asiento_viaje__asiento", "cliente"
            ),
            key=_orden_asiento,
        )
        # El modelo se toma del manager relacionado para no importar apps.encomiendas:
        # viajes esta por debajo de encomiendas en el grafo de dependencias.
        relacion_encomiendas = self.object.encomiendas
        encomiendas = list(
            relacion_encomiendas.exclude(estado__in=relacion_encomiendas.model.ESTADOS_SIN_CARGA)
            .order_by("codigo_guia")
        )
        context.update(
            {
                "pasajes": pasajes,
                "encomiendas": encomiendas,
                "peso_total_kg": sum((e.peso_kg for e in encomiendas), Decimal("0")),
                "url_volver": reverse(
                    "viajes:mis_viajes" if self.request.user.rol == "conductor" else "viajes:listado"
                ),
            }
        )
        return context
