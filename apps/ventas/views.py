from collections import defaultdict

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from apps.viajes.models import Viaje, AsientoViaje
from .forms import VentaForm
from .models import Pasaje, Pago, Comprobante

# Datos del emisor: fijos para toda la empresa (no hay multi-sucursal en el
# alcance del proyecto). Son datos ficticios para fines académicos: Trans
# Naser no está registrada ante Impuestos Nacionales de Bolivia.
EMPRESA_FISCAL = {
    "razon_social": "TRANS NASER S.R.L.",
    "nit": "0000000000000",
    "punto_venta": "Punto de Venta 0",
    "sucursal": "Casa Matriz",
    "direccion": "Terminal Bimodal, Av. del Ejército",
    "numero_autorizacion": "00000000000000000000000000000000",
}


class NuevaVentaView(View):
    template_name = "ventas/nueva_venta.html"

    def _viajes_disponibles(self):
        hoy = timezone.localdate()
        return (
            Viaje.objects.filter(fecha_salida__gte=hoy)
            .exclude(estado="cancelado")
            .select_related("ruta__origen", "ruta__destino", "bus", "horario")
            .order_by("fecha_salida", "horario__hora_salida")
        )

    def _agrupar_asientos(self, asientos_viaje):
        """Arma una estructura [(piso, [[col1,col2,col3,col4], ...]), ...] para
        dibujar el mapa 2+pasillo+2 en la plantilla sin lógica compleja ahí."""
        pisos = defaultdict(lambda: defaultdict(dict))
        for av in asientos_viaje:
            piso = av.asiento.piso or 1
            fila = av.asiento.fila or 0
            columna = av.asiento.columna or 0
            pisos[piso][fila][columna] = av

        resultado = []
        for piso in sorted(pisos):
            filas = []
            for fila in sorted(pisos[piso]):
                cols = pisos[piso][fila]
                filas.append([cols.get(1), cols.get(2), cols.get(3), cols.get(4)])
            resultado.append((piso, filas))
        return resultado

    def _contexto(self, request, form=None, viaje_seleccionado=None):
        viajes = self._viajes_disponibles()

        if viaje_seleccionado is None:
            viaje_id = request.GET.get("viaje") or request.POST.get("viaje_id")
            if viaje_id:
                viaje_seleccionado = viajes.filter(pk=viaje_id).first()
            if viaje_seleccionado is None:
                viaje_seleccionado = viajes.first()

        asientos_viaje = []
        pisos_asientos = []
        if viaje_seleccionado:
            asientos_viaje = (
                viaje_seleccionado.asientos_viaje.select_related("asiento")
                .order_by("asiento__piso", "asiento__fila", "asiento__columna")
            )
            pisos_asientos = self._agrupar_asientos(asientos_viaje)

        return {
            "viajes": viajes,
            "viaje_seleccionado": viaje_seleccionado,
            "pisos_asientos": pisos_asientos,
            "form": form or VentaForm(),
        }

    def get(self, request):
        return render(request, self.template_name, self._contexto(request))

    def post(self, request):
        viaje_id = request.POST.get("viaje_id")
        viaje = get_object_or_404(Viaje, pk=viaje_id)
        form = VentaForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                asiento_viaje = get_object_or_404(
                    AsientoViaje.objects.select_for_update(),
                    pk=form.cleaned_data["asiento_viaje_id"],
                    viaje=viaje,
                )
                if asiento_viaje.estado != "disponible":
                    form.add_error(None, "Ese asiento ya no está disponible. Elige otro.")
                else:
                    pasaje = Pasaje.objects.create(
                        viaje=viaje,
                        asiento_viaje=asiento_viaje,
                        cliente_nombre=form.cleaned_data["cliente_nombre"],
                        cliente_ci=form.cleaned_data["cliente_ci"],
                        vendido_por=request.user if request.user.is_authenticated else None,
                        actualizado_por=request.user if request.user.is_authenticated else None,
                        canal="ventanilla",
                        precio=form.cleaned_data["precio"],
                    )
                    pasaje.marcar_como_vendido()
                    Pago.objects.create(
                        pasaje=pasaje,
                        metodo=form.cleaned_data["metodo_pago"],
                        monto=form.cleaned_data["precio"],
                    )
                    Comprobante.objects.create(pasaje=pasaje, tipo="recibo")

                    messages.success(
                        request,
                        f"Pasaje {pasaje.codigo_pasaje} vendido correctamente "
                        f"(asiento {asiento_viaje.asiento.numero}).",
                    )
                    return redirect("ventas:boleto", pk=pasaje.pk)

        return render(request, self.template_name, self._contexto(request, form=form, viaje_seleccionado=viaje))


class VerBoletoView(DetailView):
    model = Pasaje
    template_name = "ventas/boleto.html"
    context_object_name = "pasaje"

    def get_queryset(self):
        return Pasaje.objects.select_related(
            "viaje__ruta__origen", "viaje__ruta__destino", "viaje__bus",
            "viaje__horario", "asiento_viaje__asiento", "comprobante", "vendido_por",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["empresa"] = EMPRESA_FISCAL
        context["pago"] = self.object.pagos.first()
        return context
