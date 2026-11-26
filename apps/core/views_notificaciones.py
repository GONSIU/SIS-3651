"""Bandeja de notificaciones del cliente (caso de uso Recibir notificaciones).

Cada vista filtra por request.user: un cliente nunca ve ni borra avisos de otra cuenta
(un pk ajeno responde 404, no 403, para no revelar que existe)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView

from apps.core.mixins import RolRequeridoMixin
from apps.core.models import Notificacion

ROLES_BANDEJA = ["cliente"]


class BandejaNotificacionesView(RolRequeridoMixin, ListView):
    roles_permitidos = ROLES_BANDEJA
    template_name = "core/notificaciones/bandeja.html"
    context_object_name = "notificaciones"
    paginate_by = 20

    def get_queryset(self):
        return Notificacion.objects.filter(usuario=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sin_leer"] = Notificacion.objects.filter(usuario=self.request.user, leida=False).count()
        return context


class DetalleNotificacionView(RolRequeridoMixin, DetailView):
    """Muestra el aviso completo y lo marca como leido."""

    roles_permitidos = ROLES_BANDEJA
    template_name = "core/notificaciones/detalle.html"
    context_object_name = "notificacion"

    def get_queryset(self):
        return Notificacion.objects.filter(usuario=self.request.user)

    def get_object(self, queryset=None):
        notificacion = super().get_object(queryset)
        notificacion.marcar_leida()
        return notificacion


class EliminarNotificacionView(RolRequeridoMixin, View):
    roles_permitidos = ROLES_BANDEJA
    http_method_names = ["post"]

    def post(self, request, pk: int):
        get_object_or_404(Notificacion, pk=pk, usuario=request.user).delete()
        messages.success(request, "Notificacion eliminada.")
        return redirect("core:notificaciones")


class MarcarTodasLeidasView(RolRequeridoMixin, View):
    roles_permitidos = ROLES_BANDEJA
    http_method_names = ["post"]

    def post(self, request):
        cantidad = Notificacion.objects.filter(usuario=request.user, leida=False).update(leida=True)
        if cantidad:
            messages.success(request, f"{cantidad} notificacion(es) marcadas como leidas.")
        return redirect("core:notificaciones")
