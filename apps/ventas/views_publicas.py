"""Consulta publica de viajes y asientos: no exige sesion.

Estas vistas estan en VISTAS_PUBLICAS (apps/core/middleware.py). Solo muestran datos
del viaje y el estado de cada asiento; nunca datos de pasajeros."""

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import DetailView, TemplateView

from .forms import BuscarViajeForm
from .services import CIERRE_RESERVA_ONLINE, liberar_reservas_vencidas, mapa_de_asientos, viajes_reservables_online

# Cada cuanto la pagina pide el mapa actualizado.
INTERVALO_ACTUALIZACION_MS = 15_000


class BuscarViajesView(TemplateView):
    template_name = "ventas/publico/buscar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = BuscarViajeForm(self.request.GET or None)
        viajes = viajes_reservables_online()
        if form.is_bound and form.is_valid():
            viajes = form.filtrar(viajes)
        context.update(
            {
                "form": form if form.is_bound else BuscarViajeForm(),
                "viajes": viajes if not form.is_bound or form.is_valid() else viajes.none(),
                "horas_cierre": int(CIERRE_RESERVA_ONLINE.total_seconds() // 3600),
            }
        )
        return context


class ViajeReservableMixin:
    """Solo viajes reservables online; otro (o uno que dejo de serlo) da 404.

    Libera antes las reservas vencidas del viaje para que el mapa no las muestre ocupadas."""

    context_object_name = "viaje"

    def get_queryset(self):
        return viajes_reservables_online()

    def get_object(self, queryset=None):
        viaje = super().get_object(queryset)
        if liberar_reservas_vencidas(viaje=viaje):
            # Los conteos anotados ya no son validos: se vuelve a leer el viaje.
            viaje = super().get_object(queryset)
        return viaje

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pisos_asientos"] = mapa_de_asientos(self.object)
        return context


class ViajePublicoView(ViajeReservableMixin, DetailView):
    template_name = "ventas/publico/viaje.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "url_mapa": reverse("ventas:mapa_publico", args=[self.object.pk]),
                "intervalo_ms": INTERVALO_ACTUALIZACION_MS,
                "url_login": f"{reverse('usuarios:login')}?next={self.request.path}",
            }
        )
        return context


@method_decorator(never_cache, name="dispatch")
class MapaPublicoView(ViajeReservableMixin, DetailView):
    """Fragmento HTML del mapa que la pagina pide cada INTERVALO_ACTUALIZACION_MS.

    never_cache: el navegador o un proxy no deben guardar una version vieja."""

    template_name = "ventas/publico/_mapa.html"
