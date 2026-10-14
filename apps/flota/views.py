from django.contrib import messages
from django.views.generic import ListView, CreateView
from django.urls import reverse_lazy
from .models import Bus
from .forms import BusForm


class ListaFlotaView(ListView):
    model = Bus
    template_name = "flota/listado.html"
    context_object_name = "buses"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_buses"] = Bus.objects.count()
        context["total_activos"] = Bus.objects.filter(estado="activo").count()
        context["total_mantenimiento"] = Bus.objects.filter(estado="mantenimiento").count()
        return context


class NuevoBusView(CreateView):
    model = Bus
    form_class = BusForm
    template_name = "flota/nuevo.html"
    success_url = reverse_lazy("flota:listado")

    def form_valid(self, form):
        response = super().form_valid(form)
        self.object.crear_asientos()
        messages.success(
            self.request,
            f"Bus {self.object.placa} registrado con {self.object.capacidad_pasajeros} asientos.",
        )
        return response
    