from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from apps.core.mixins import RolRequeridoMixin
from apps.viajes.models import Viaje, AsientoViaje
from .forms import VentaForm
from .models import Pasaje
from .services import (
    DatosPago,
    DatosPasajero,
    buscar_pasajero_por_ci,
    con_conteo_de_asientos,
    liberar_reservas_vencidas,
    mapa_de_asientos,
    registrar_venta,
)

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


class NuevaVentaView(RolRequeridoMixin, View):
    roles_permitidos = ["ventanillero", "supervisor", "admin"]
    template_name = "ventas/nueva_venta.html"

    def _fecha_filtro(self, request) -> tuple[date | None, bool]:
        """Lee ?fecha=YYYY-MM-DD (o el campo oculto del POST). Devuelve (fecha, invalida)."""
        texto = (request.GET.get("fecha") or request.POST.get("fecha") or "").strip()
        if not texto:
            return None, False
        try:
            return date.fromisoformat(texto), False
        except ValueError:
            return None, True

    def _viajes_disponibles(self, fecha: date | None = None):
        hoy = timezone.localdate()
        viajes = (
            Viaje.objects.filter(fecha_salida__gte=hoy)
            .exclude(estado__in=Viaje.ESTADOS_SIN_VENTA)
            .select_related("ruta__origen", "ruta__destino", "bus", "horario")
            .order_by("fecha_salida", "horario__hora_salida")
        )
        # Conteos en la misma consulta: antes la plantilla hacia un count() por fila
        # y mostraba el total de asientos como si fueran los libres.
        viajes = con_conteo_de_asientos(viajes)
        if fecha:
            viajes = viajes.filter(fecha_salida=fecha)
        return viajes

    def _busqueda_por_ci(self, request) -> dict:
        """?ci_buscar=... precarga los datos del pasajero. No guarda nada."""
        ci_texto = request.GET.get("ci_buscar", "").strip()
        if not ci_texto:
            return {}
        try:
            encontrado = buscar_pasajero_por_ci(ci_texto)
        except ValidationError as error:
            return {"ci_buscado": ci_texto, "error": error.messages[0]}
        return {"ci_buscado": ci_texto, "encontrado": encontrado}

    def _contexto(self, request, form=None, viaje_seleccionado=None):
        fecha, fecha_invalida = self._fecha_filtro(request)
        viajes = self._viajes_disponibles(fecha)

        if viaje_seleccionado is None:
            viaje_id = request.GET.get("viaje") or request.POST.get("viaje_id")
            if viaje_id:
                viaje_seleccionado = viajes.filter(pk=viaje_id).first()
            if viaje_seleccionado is None:
                viaje_seleccionado = viajes.first()

        pisos_asientos = mapa_de_asientos(viaje_seleccionado) if viaje_seleccionado else []

        busqueda = self._busqueda_por_ci(request)
        if form is None:
            form = VentaForm(initial=self._datos_iniciales(viaje_seleccionado, busqueda))

        return {
            "viajes": viajes,
            "viaje_seleccionado": viaje_seleccionado,
            "pisos_asientos": pisos_asientos,
            "form": form,
            "fecha": fecha,
            "fecha_invalida": fecha_invalida,
            "busqueda": busqueda,
        }

    @staticmethod
    def _datos_iniciales(viaje, busqueda: dict) -> dict:
        """Precio base de la ruta y, si se busco un CI, los datos del pasajero."""
        iniciales = {}
        if viaje and viaje.ruta.precio_base:
            iniciales["precio"] = viaje.ruta.precio_base
        encontrado = busqueda.get("encontrado")
        if encontrado:
            iniciales.update(
                {"cliente_nombre": encontrado.nombre, "cliente_ci": encontrado.ci, "telefono": encontrado.telefono}
            )
        elif busqueda and not busqueda.get("error"):
            # No se encontro: al menos se deja el CI escrito para no teclearlo dos veces.
            iniciales["cliente_ci"] = busqueda["ci_buscado"]
        return iniciales

    def get(self, request):
        # Antes de contar asientos libres, para que una reserva vencida no figure ocupada.
        liberar_reservas_vencidas()
        return render(request, self.template_name, self._contexto(request))

    def post(self, request):
        viaje_id = request.POST.get("viaje_id")
        viaje = get_object_or_404(Viaje, pk=viaje_id)
        form = VentaForm(request.POST)

        if form.is_valid():
            datos = form.cleaned_data
            # Un asiento de otro viaje es una peticion manipulada: 404, como antes.
            get_object_or_404(AsientoViaje, pk=datos["asiento_viaje_id"], viaje=viaje)
            try:
                pasaje = registrar_venta(
                    viaje=viaje,
                    asiento_viaje_id=datos["asiento_viaje_id"],
                    pasajero=DatosPasajero(
                        nombre=datos["cliente_nombre"], ci=datos["cliente_ci"], telefono=datos["telefono"]
                    ),
                    precio=datos["precio"],
                    pago=DatosPago(
                        metodo=datos["metodo_pago"], monto=datos["precio"], referencia=datos["referencia_externa"]
                    ),
                    vendido_por=request.user,
                )
            except ValidationError as error:
                for mensaje in error.messages:
                    form.add_error(None, mensaje)
            else:
                messages.success(
                    request,
                    f"Pasaje {pasaje.codigo_pasaje} vendido correctamente "
                    f"(asiento {pasaje.asiento_viaje.asiento.numero}).",
                )
                return redirect("ventas:boleto", pk=pasaje.pk)

        return render(request, self.template_name, self._contexto(request, form=form, viaje_seleccionado=viaje))


class VerBoletoView(RolRequeridoMixin, DetailView):
    """Boleto (pagado) o comprobante de reserva (con saldo pendiente).

    Un cliente solo ve los pasajes de su cuenta: otro da 404, no 403, para no revelar
    que existe."""

    roles_permitidos = ["ventanillero", "supervisor", "admin", "cliente"]
    model = Pasaje
    template_name = "ventas/boleto.html"
    context_object_name = "pasaje"

    def get_queryset(self):
        pasajes = Pasaje.objects.select_related(
            "viaje__ruta__origen", "viaje__ruta__destino", "viaje__bus",
            "viaje__horario", "asiento_viaje__asiento", "comprobante", "vendido_por",
        ).prefetch_related("pagos")
        if self.request.user.rol == "cliente":
            pasajes = pasajes.filter(cliente=self.request.user)
        return pasajes

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["empresa"] = EMPRESA_FISCAL
        context["pagos"] = list(self.object.pagos.all())
        context["url_volver"] = reverse(
            "ventas:mis_pasajes" if self.request.user.rol == "cliente" else "ventas:nueva_venta"
        )
        return context
