from django.contrib import messages
from django.views.generic import ListView, CreateView
from django.urls import reverse_lazy
from .models import Viaje
from .forms import ViajeForm


class ListaViajesView(ListView):
    model = Viaje
    template_name = "viajes/listado.html"
    context_object_name = "viajes"

    def get_queryset(self):
        return (
            Viaje.objects.select_related("ruta__origen", "ruta__destino", "bus", "horario")
            .order_by("-fecha_salida", "horario__hora_salida")[:50]
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for viaje in context["viajes"]:
            total = viaje.asientos_viaje.count()
            vendidos = viaje.asientos_viaje.filter(estado="vendido").count()
            viaje.ocupacion_texto = f"{vendidos}/{total}" if total else "—"
        return context


class NuevoViajeView(CreateView):
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
    