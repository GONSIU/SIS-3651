from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from apps.core.mixins import RolRequeridoMixin
from apps.core.models import Notificacion
from .forms import IncidenciaForm, ReclamoForm
from .models import Incidencia

ROLES_GESTION = ["supervisor", "admin"]


class ListaIncidenciasView(RolRequeridoMixin, ListView):
    """Historial de incidencias y reclamos. Filtros: ?estado=, ?categoria=, ?q= (codigo,
    titulo o descripcion)."""

    roles_permitidos = ROLES_GESTION
    template_name = "incidencias/listado.html"
    context_object_name = "incidencias"
    paginate_by = 20

    def get_queryset(self):
        incidencias = Incidencia.objects.select_related("reportado_por", "bus", "viaje__ruta__origen", "viaje__ruta__destino")
        estado = self.request.GET.get("estado", "")
        if estado in Incidencia.TRANSICIONES:
            incidencias = incidencias.filter(estado=estado)
        categoria = self.request.GET.get("categoria", "")
        if categoria in dict(Incidencia.CATEGORIA_CHOICES):
            incidencias = incidencias.filter(categoria=categoria)
        busqueda = self.request.GET.get("q", "").strip()
        if busqueda:
            incidencias = incidencias.filter(
                Q(codigo__icontains=busqueda) | Q(titulo__icontains=busqueda) | Q(descripcion__icontains=busqueda)
            )
        return incidencias

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["totales"] = Incidencia.objects.aggregate(
            abiertas=Count("pk", filter=Q(estado="abierta")),
            en_revision=Count("pk", filter=Q(estado="en_revision")),
            resueltas=Count("pk", filter=Q(estado="resuelta")),
            reclamos_pendientes=Count(
                "pk",
                filter=Q(categoria__in=Incidencia.CATEGORIAS_CLIENTE, estado__in=Incidencia.ESTADOS_PENDIENTES),
            ),
        )
        context["estados"] = Incidencia.ESTADO_CHOICES
        context["categorias"] = Incidencia.CATEGORIA_CHOICES
        context["estado_actual"] = self.request.GET.get("estado", "")
        context["categoria_actual"] = self.request.GET.get("categoria", "")
        context["busqueda"] = self.request.GET.get("q", "")
        return context


class NuevaIncidenciaView(RolRequeridoMixin, CreateView):
    roles_permitidos = ROLES_GESTION
    model = Incidencia
    form_class = IncidenciaForm
    template_name = "incidencias/nueva.html"

    def form_valid(self, form):
        form.instance.reportado_por = self.request.user
        respuesta = super().form_valid(form)
        messages.success(self.request, f"Incidencia {self.object.codigo} registrada.")
        return respuesta

    def get_success_url(self):
        return reverse("incidencias:detalle", args=[self.object.pk])


class DetalleIncidenciaView(RolRequeridoMixin, DetailView):
    roles_permitidos = ROLES_GESTION
    model = Incidencia
    template_name = "incidencias/detalle.html"
    context_object_name = "incidencia"

    def get_queryset(self):
        return Incidencia.objects.select_related(
            "reportado_por", "resuelta_por", "bus", "empleado_involucrado__usuario",
            "viaje__ruta__origen", "viaje__ruta__destino", "viaje__horario", "pasaje",
        )


class CambiarEstadoIncidenciaView(RolRequeridoMixin, View):
    """Pasa la incidencia a "en revision" o "resuelta" (solo POST)."""

    roles_permitidos = ROLES_GESTION
    http_method_names = ["post"]

    def post(self, request, pk: int):
        with transaction.atomic():
            incidencia = get_object_or_404(Incidencia.objects.select_for_update(), pk=pk)
            try:
                incidencia.cambiar_estado(
                    request.POST.get("estado", ""), request.user, request.POST.get("resolucion", "")
                )
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
            else:
                messages.success(
                    request, f"Incidencia {incidencia.codigo}: {incidencia.get_estado_display().lower()}."
                )
        return redirect("incidencias:detalle", pk=pk)


# --- Reclamos del cliente ---------------------------------------------------------


class MisReclamosView(RolRequeridoMixin, ListView):
    """Reclamos y comentarios de la cuenta, con su estado y la respuesta (subflujo A1 del
    caso de uso Realizar reclamos: consultar el estado de un reclamo anterior)."""

    roles_permitidos = ["cliente"]
    template_name = "incidencias/cliente/mis_reclamos.html"
    context_object_name = "reclamos"

    def get_queryset(self):
        return Incidencia.objects.filter(reportado_por=self.request.user).select_related("pasaje")


class NuevoReclamoView(RolRequeridoMixin, CreateView):
    roles_permitidos = ["cliente"]
    model = Incidencia
    form_class = ReclamoForm
    template_name = "incidencias/cliente/nuevo_reclamo.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["cliente"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        pasaje = self.request.GET.get("pasaje", "")
        if pasaje.isdigit():
            initial["pasaje"] = int(pasaje)
        return initial

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.reportado_por = self.request.user
            respuesta = super().form_valid(form)
            Notificacion.avisar(
                self.request.user.pk,
                f"Recibimos tu {'reclamo' if self.object.categoria == 'reclamo' else 'comentario'}",
                f"Ticket de seguimiento {self.object.codigo}. Te avisaremos cuando lo revisemos.",
                reverse("incidencias:mis_reclamos"),
            )
        messages.success(self.request, f"Enviado. Tu ticket de seguimiento es {self.object.codigo}.")
        return respuesta

    def get_success_url(self):
        return reverse("incidencias:mis_reclamos")
