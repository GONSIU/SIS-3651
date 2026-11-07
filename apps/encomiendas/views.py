from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, ListView

from apps.ventas.views import EMPRESA_FISCAL
from apps.viajes.models import Viaje
from .forms import EncomiendaForm
from .models import ComprobanteEncomienda, Encomienda, PagoEncomienda

# Todas las vistas exigen sesion: la encomienda guarda quien la registro (registrado_por es NOT NULL).


class ListaEncomiendasView(LoginRequiredMixin, ListView):
    model = Encomienda
    template_name = "encomiendas/listado.html"
    context_object_name = "encomiendas"
    paginate_by = 20

    def get_queryset(self):
        queryset = Encomienda.objects.select_related("viaje__ruta__origen", "viaje__ruta__destino")
        estado = self.request.GET.get("estado")
        if estado in Encomienda.TRANSICIONES:
            queryset = queryset.filter(estado=estado)
        busqueda = self.request.GET.get("q", "").strip()
        if busqueda:
            queryset = queryset.filter(
                Q(codigo_guia__icontains=busqueda)
                | Q(remitente_nombre__icontains=busqueda)
                | Q(destinatario_nombre__icontains=busqueda)
                | Q(remitente_ci__icontains=busqueda)
                | Q(destinatario_ci__icontains=busqueda)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["estados"] = Encomienda.ESTADO_CHOICES
        context["estado_actual"] = self.request.GET.get("estado", "")
        context["busqueda"] = self.request.GET.get("q", "")
        return context


class NuevaEncomiendaView(LoginRequiredMixin, View):
    template_name = "encomiendas/nueva.html"

    def _contexto(self, form: EncomiendaForm) -> dict:
        return {
            "form": form,
            "tarifa": {
                "flete_base": str(Encomienda.FLETE_BASE),
                "por_kg": str(Encomienda.TARIFA_POR_KG),
                "tasa_seguro": str(Encomienda.TASA_SEGURO),
            },
        }

    def get(self, request):
        return render(request, self.template_name, self._contexto(EncomiendaForm()))

    def post(self, request):
        form = EncomiendaForm(request.POST, request.FILES)
        with transaction.atomic():
            # Bloquea el viaje antes de validar: la regla de capacidad suma la carga del
            # viaje, y sin el bloqueo dos registros simultaneos podrian superarla.
            viaje_id = request.POST.get("viaje", "")
            if viaje_id.isdigit():
                Viaje.objects.select_for_update().filter(pk=viaje_id).first()

            if form.is_valid():
                encomienda = form.save(commit=False)
                encomienda.registrado_por = request.user
                encomienda.actualizado_por = request.user
                encomienda.save()

                pago = PagoEncomienda(
                    encomienda=encomienda,
                    metodo=form.cleaned_data["metodo_pago"],
                    monto=encomienda.precio_envio,
                    referencia_externa=form.cleaned_data["referencia_externa"],
                )
                pago.full_clean()
                pago.save()
                ComprobanteEncomienda.objects.create(encomienda=encomienda)

                messages.success(request, f"Encomienda {encomienda.codigo_guia} registrada.")
                return redirect("encomiendas:guia", pk=encomienda.pk)

        return render(request, self.template_name, self._contexto(form))


class GuiaEncomiendaView(LoginRequiredMixin, DetailView):
    model = Encomienda
    template_name = "encomiendas/guia.html"
    context_object_name = "encomienda"

    def get_queryset(self):
        return Encomienda.objects.select_related(
            "viaje__ruta__origen", "viaje__ruta__destino", "viaje__bus", "viaje__horario",
            "comprobante", "registrado_por",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["empresa"] = EMPRESA_FISCAL
        context["pago"] = self.object.pagos.first()
        return context


class CambiarEstadoView(LoginRequiredMixin, View):
    def post(self, request, pk):
        with transaction.atomic():
            encomienda = get_object_or_404(Encomienda.objects.select_for_update(), pk=pk)
            try:
                encomienda.cambiar_estado(request.POST.get("estado", ""), request.user)
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                messages.success(
                    request,
                    f"Encomienda {encomienda.codigo_guia}: {encomienda.get_estado_display().lower()}.",
                )
        return redirect("encomiendas:listado")
