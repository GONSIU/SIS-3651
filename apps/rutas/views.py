from django.contrib import messages
from django.db import transaction
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.core.mixins import RolRequeridoMixin
from .models import Terminal, Ruta, Horario
from .forms import TerminalForm, RutaForm, HorarioForm


class ListaRutasView(RolRequeridoMixin, ListView):
    roles_permitidos = ["supervisor", "admin"]
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


class NuevaRutaView(RolRequeridoMixin, CreateView):
    roles_permitidos = ["supervisor", "admin"]
    model = Ruta
    form_class = RutaForm
    template_name = "rutas/nuevo.html"
    success_url = reverse_lazy("rutas:listado")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Ruta {self.object} registrada.")
        return response


class NuevaTerminalView(RolRequeridoMixin, CreateView):
    roles_permitidos = ["supervisor", "admin"]
    model = Terminal
    form_class = TerminalForm
    template_name = "rutas/terminal_nuevo.html"
    # Vuelve a Nueva Ruta para retomar el flujo con el terminal ya disponible en los select
    success_url = reverse_lazy("rutas:nuevo")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Terminal {self.object} registrado.")
        return response


class ListaHorariosView(RolRequeridoMixin, ListView):
    roles_permitidos = ["supervisor", "admin"]
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


class NuevoHorarioView(RolRequeridoMixin, CreateView):
    roles_permitidos = ["supervisor", "admin"]
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


# --- Edicion, eliminacion y activacion -------------------------------------------
# Una ruta o un horario con viajes no se borra (Viaje.ruta y Viaje.horario son
# PROTECT): se desactiva. Desactivar solo impide programar viajes nuevos.


def _viajes_pendientes(objeto) -> int:
    """Viajes no cancelados desde hoy: siguen vigentes aunque se desactive el objeto."""
    return (
        objeto.viajes.filter(fecha_salida__gte=timezone.localdate())
        .exclude(estado__in=["cancelado", "completado"])
        .count()
    )


class EditarRutaView(RolRequeridoMixin, UpdateView):
    roles_permitidos = ["supervisor", "admin"]
    model = Ruta
    form_class = RutaForm
    template_name = "rutas/nuevo.html"
    success_url = reverse_lazy("rutas:listado")

    def get_queryset(self):
        return Ruta.objects.select_related("origen", "destino")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["editando"] = True
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Ruta {self.object} actualizada.")
        return response


class EliminarObjetoMixin:
    """Confirmacion (GET) y borrado (POST) que no borra si hay viajes.

    El chequeo previo evita mostrar un boton que va a fallar; el except cubre el caso
    de que alguien programe un viaje entre la confirmacion y el borrado."""

    template_name = "rutas/confirmar_eliminar.html"
    tipo = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "tipo": self.tipo,
                "bloqueado": self.object.tiene_viajes(),
                "detalle": self.detalle(),
                "url_cancelar": self.get_success_url(),
                "url_activar": self.url_activar(),
            }
        )
        return context

    def form_valid(self, form):
        nombre = str(self.object)
        if self.object.tiene_viajes():
            messages.error(self.request, f"No se puede eliminar {self.tipo} {nombre}: tiene viajes. Usa Desactivar en su lugar.")
            return redirect(self.get_success_url())
        try:
            self.object.delete()
        except ProtectedError:
            messages.error(self.request, f"No se puede eliminar {self.tipo} {nombre}: tiene viajes.")
        else:
            messages.success(self.request, f"Se elimino {self.tipo} {nombre}.")
        return redirect(self.get_success_url())


class EliminarRutaView(RolRequeridoMixin, EliminarObjetoMixin, DeleteView):
    roles_permitidos = ["supervisor", "admin"]
    model = Ruta
    tipo = "la ruta"
    success_url = reverse_lazy("rutas:listado")

    def detalle(self) -> str:
        return f"Tambien se eliminan sus {self.object.horarios.count()} horario(s)."

    def url_activar(self) -> str:
        return reverse("rutas:activar", args=[self.object.pk])


class CambiarActivaRutaView(RolRequeridoMixin, View):
    """Activa o desactiva la ruta (solo POST)."""

    roles_permitidos = ["supervisor", "admin"]
    http_method_names = ["post"]

    def post(self, request, pk: int):
        with transaction.atomic():
            ruta = get_object_or_404(Ruta.objects.select_for_update(), pk=pk)
            ruta.activa = not ruta.activa
            ruta.save(update_fields=["activa", "updated_at"])
        if ruta.activa:
            messages.success(request, f"Ruta {ruta} activada.")
        else:
            messages.success(
                request,
                f"Ruta {ruta} desactivada: no se programaran viajes nuevos. "
                f"Sus {_viajes_pendientes(ruta)} viaje(s) pendientes siguen vigentes.",
            )
        return redirect("rutas:listado")


class EditarHorarioView(RolRequeridoMixin, UpdateView):
    roles_permitidos = ["supervisor", "admin"]
    model = Horario
    form_class = HorarioForm
    template_name = "rutas/horario_nuevo.html"

    def get_queryset(self):
        return Horario.objects.select_related("ruta__origen", "ruta__destino")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"ruta": self.object.ruta, "editando": True})
        return context

    def get_success_url(self):
        return reverse("rutas:horarios", kwargs={"ruta_id": self.object.ruta_id})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Horario {self.object.hora_salida:%H:%M} actualizado.")
        return response


class EliminarHorarioView(RolRequeridoMixin, EliminarObjetoMixin, DeleteView):
    roles_permitidos = ["supervisor", "admin"]
    model = Horario
    tipo = "el horario"

    def get_queryset(self):
        return Horario.objects.select_related("ruta__origen", "ruta__destino")

    def get_success_url(self):
        return reverse("rutas:horarios", kwargs={"ruta_id": self.object.ruta_id})

    def detalle(self) -> str:
        return f"Ruta {self.object.ruta}, dias {self.object.dias_semana}."

    def url_activar(self) -> str:
        return reverse("rutas:horario_activar", args=[self.object.pk])


class CambiarActivoHorarioView(RolRequeridoMixin, View):
    """Activa o desactiva el horario (solo POST)."""

    roles_permitidos = ["supervisor", "admin"]
    http_method_names = ["post"]

    def post(self, request, pk: int):
        with transaction.atomic():
            horario = get_object_or_404(Horario.objects.select_for_update(), pk=pk)
            horario.activo = not horario.activo
            horario.save(update_fields=["activo", "updated_at"])
        etiqueta = f"Horario {horario.hora_salida:%H:%M}"
        if horario.activo:
            messages.success(request, f"{etiqueta} activado.")
        else:
            messages.success(
                request,
                f"{etiqueta} desactivado: no se programaran viajes nuevos. "
                f"Sus {_viajes_pendientes(horario)} viaje(s) pendientes siguen vigentes.",
            )
        return redirect("rutas:horarios", ruta_id=horario.ruta_id)
