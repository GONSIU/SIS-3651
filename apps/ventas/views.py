from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.generic import DetailView, ListView

from apps.core.mixins import RolRequeridoMixin
from apps.viajes.models import Viaje, AsientoViaje
from .forms import CobrarSaldoForm, VentaForm
from .models import Pasaje
from .services import (
    DatosFacturacion,
    DatosPago,
    DatosPasajero,
    buscar_pasajero_por_ci,
    cobrar_saldo,
    reservas_pendientes,
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
                    facturacion=DatosFacturacion(nit=datos["nit"], razon_social=datos["razon_social"]),
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


class ReservasPendientesView(RolRequeridoMixin, ListView):
    """Reservas online con saldo por cobrar. ?q= busca por codigo de pasaje o CI."""

    roles_permitidos = ["ventanillero", "supervisor", "admin"]
    template_name = "ventas/reservas_pendientes.html"
    context_object_name = "reservas"

    def get_queryset(self):
        self.consulta = self.request.GET.get("q", "").strip()
        reservas = reservas_pendientes()
        if self.consulta:
            texto = self.consulta.upper().replace(" ", "")
            reservas = reservas.filter(
                Q(codigo_pasaje__iexact=self.consulta) | Q(cliente_ci=texto) | Q(cliente__ci=texto)
            )
        return reservas

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.consulta
        return context


class CobrarSaldoView(RolRequeridoMixin, View):
    """Muestra la reserva y cobra el saldo. El monto es el saldo del servidor."""

    roles_permitidos = ["ventanillero", "supervisor", "admin"]
    template_name = "ventas/cobrar_saldo.html"

    def _reserva(self, pk: int) -> Pasaje:
        return get_object_or_404(reservas_pendientes(), pk=pk)

    def _render(self, request, reserva: Pasaje, form: CobrarSaldoForm):
        return render(request, self.template_name, {"reserva": reserva, "form": form})

    def get(self, request, pk: int):
        reserva = self._reserva(pk)
        comprobante = getattr(reserva, "comprobante", None)
        inicial = {"metodo": "efectivo"}
        if comprobante:
            inicial.update({"nit": comprobante.nit_cliente, "razon_social": comprobante.razon_social_cliente})
        return self._render(request, reserva, CobrarSaldoForm(initial=inicial))

    def post(self, request, pk: int):
        reserva = self._reserva(pk)
        form = CobrarSaldoForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            try:
                pasaje = cobrar_saldo(
                    pasaje_id=reserva.pk,
                    pago=DatosPago(metodo=datos["metodo"], monto=reserva.saldo, referencia=datos["referencia"]),
                    cobrado_por=request.user,
                    facturacion=DatosFacturacion(nit=datos["nit"], razon_social=datos["razon_social"]),
                )
            except ValidationError as error:
                for mensaje in error.messages:
                    form.add_error(None, mensaje)
            else:
                messages.success(request, f"Saldo cobrado. Pasaje {pasaje.codigo_pasaje} pagado.")
                return redirect("ventas:boleto", pk=pasaje.pk)
        return self._render(request, reserva, form)


@method_decorator(never_cache, name="dispatch")
class BuscarPasajeroView(RolRequeridoMixin, View):
    """GET ?ci=... -> JSON con los datos para llenar la venta en ventanilla.

    Solo personal: un cliente no puede consultar a quien pertenece un CI (en la reserva
    online el nombre se valida sin revelarlo). Es la unica vista JSON del proyecto: la
    usa el JavaScript del formulario de venta; sin JavaScript sigue el boton Buscar."""

    roles_permitidos = ["ventanillero", "supervisor", "admin"]

    def get(self, request):
        try:
            encontrado = buscar_pasajero_por_ci(request.GET.get("ci", ""))
        except ValidationError:
            return JsonResponse({"valido": False, "encontrado": False})
        if encontrado is None:
            return JsonResponse({"valido": True, "encontrado": False})
        return JsonResponse(
            {
                "valido": True,
                "encontrado": True,
                "nombre": encontrado.nombre,
                "telefono": encontrado.telefono,
                "tiene_cuenta": encontrado.tiene_cuenta,
            }
        )
