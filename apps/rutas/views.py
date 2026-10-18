from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.views.generic import ListView, CreateView
from django.urls import reverse, reverse_lazy
from .models import Terminal, Ruta, Horario
from .forms import TerminalForm, RutaForm, HorarioForm


class ListaRutasView(ListView):
    model = Ruta
    template_name = "rutas/listado.html"
    context_object_name = "rutas"

    def get_queryset(self):
        return (
            Ruta.objects.select_related("origen", "destino")
            .annotate(num_horarios=Count("horarios"))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_rutas"] = Ruta.objects.count()
        context["total_activas"] = Ruta.objects.filter(activa=True).count()
        context["total_horarios"] = Horario.objects.count()
        return context


class NuevaRutaView(CreateView):
    model = Ruta
    form_class = RutaForm
    template_name = "rutas/nuevo.html"
    success_url = reverse_lazy("rutas:listado")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Ruta {self.object} registrada.")
        return response


class NuevaTerminalView(CreateView):
    model = Terminal
    form_class = TerminalForm
    template_name = "rutas/terminal_nuevo.html"
    # Vuelve a Nueva Ruta para retomar el flujo con el terminal ya disponible en los select
    success_url = reverse_lazy("rutas:nuevo")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Terminal {self.object} registrado.")
        return response


class ListaHorariosView(ListView):
    model = Horario
    template_name = "rutas/horarios_listado.html"
    context_object_name = "horarios"

    def get_queryset(self):
        self.ruta = get_object_or_404(
            Ruta.objects.select_related("origen", "destino"), pk=self.kwargs["ruta_id"]
        )
        return self.ruta.horarios.order_by("hora_salida")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ruta"] = self.ruta
        return context


class NuevoHorarioView(CreateView):
    model = Horario
    form_class = HorarioForm
    template_name = "rutas/horario_nuevo.html"

    def dispatch(self, request, *args, **kwargs):
        self.ruta = get_object_or_404(
            Ruta.objects.select_related("origen", "destino"), pk=kwargs["ruta_id"]
        )
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial["ruta"] = self.ruta
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ruta"] = self.ruta
        return context

    def get_success_url(self):
        # Se usa la ruta guardada, no la de la URL, por si el usuario cambio el select
        return reverse("rutas:horarios", kwargs={"ruta_id": self.object.ruta_id})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Horario {self.object.hora_salida:%H:%M} agregado a {self.object.ruta}.",
        )
        return response
