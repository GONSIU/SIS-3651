from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.generic import DetailView, ListView

from apps.core.mixins import RolRequeridoMixin
from apps.viajes.models import Viaje, AsientoViaje
from .forms import CobrarSaldoForm, ReprogramarForm, VentaForm
from .models import Pasaje
from .pdf import pdf_boleto
from .qr import MONTO_MAXIMO, PATRON_REFERENCIA, contenido_boleto_qr, data_uri_svg, svg_pago_qr, svg_qr
from .services import (
    DatosFacturacion,
    DatosPago,
    DatosPasajero,
    PLAZO_REPROGRAMACION,
    buscar_pasajero_por_ci,
    calcular_reprogramacion,
    cobrar_saldo,
    motivo_no_reprogramable,
    pasajes_reprogramables,
    reprogramar_pasaje,
    reservas_pendientes,
    liberar_reservas_vencidas,
    mapa_de_asientos,
    registrar_venta,
    viajes_vendibles,
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
        return viajes_vendibles(fecha)

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
            "viaje__horario", "asiento_viaje__asiento", "comprobante", "vendido_por", "reprogramado_de",
        ).prefetch_related("pagos")
        if self.request.user.rol == "cliente":
            pasajes = pasajes.filter(cliente=self.request.user)
        return pasajes

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["empresa"] = EMPRESA_FISCAL
        context["pagos"] = list(self.object.pagos.all())
        # Incrustado como data URI: el boleto se imprime sin pedir otra imagen al servidor.
        context["qr_boleto"] = data_uri_svg(svg_qr(contenido_boleto_qr(self.object), tamano=128))
        context["url_volver"] = reverse(
            "ventas:mis_pasajes" if self.request.user.rol == "cliente" else "ventas:nueva_venta"
        )
        return context


class BoletoPdfView(VerBoletoView):
    """Descarga el boleto en PDF. Hereda permisos y queryset de VerBoletoView: un cliente
    solo descarga sus propios pasajes (los ajenos dan 404)."""

    def get(self, request, *args, **kwargs):
        pasaje = self.get_object()
        respuesta = HttpResponse(pdf_boleto(pasaje, EMPRESA_FISCAL), content_type="application/pdf")
        respuesta["Content-Disposition"] = f'attachment; filename="boleto-{pasaje.codigo_pasaje}.pdf"'
        return respuesta


class ReservasPendientesView(RolRequeridoMixin, ListView):
    """Reservas online con saldo por cobrar. ?q= busca por codigo de pasaje o CI."""

    roles_permitidos = ["ventanillero", "supervisor", "admin"]
    template_name = "ventas/reservas_pendientes.html"
    context_object_name = "reservas"

    def get_queryset(self):
        self.consulta = self.request.GET.get("q", "").strip()
        return _filtrar_por_codigo_o_ci(reservas_pendientes(), self.consulta)

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


class QrPagoView(RolRequeridoMixin, View):
    """GET ?monto=40.00&ref=QR-AB12CD34 -> imagen SVG del QR de pago (ficticio).

    La pide static/js/pago_qr.js al elegir QR. Solo dibuja: no guarda nada ni cobra. Se
    validan monto y referencia para no dibujar cualquier texto que llegue en la URL."""

    # Quienes ven un formulario de pago: personal de ventanilla y el cliente al reservar.
    roles_permitidos = ["ventanillero", "supervisor", "admin", "cliente"]

    def get(self, request):
        referencia = request.GET.get("ref", "")
        try:
            monto = Decimal(request.GET.get("monto", ""))
        except InvalidOperation:
            return HttpResponseBadRequest("Monto no valido.")
        if not (Decimal("0.01") <= monto <= MONTO_MAXIMO) or not PATRON_REFERENCIA.match(referencia):
            return HttpResponseBadRequest("Monto o referencia no validos.")
        respuesta = HttpResponse(svg_pago_qr(monto.quantize(Decimal("0.01")), referencia), content_type="image/svg+xml")
        # Mismo monto y referencia dan el mismo QR: el navegador puede reutilizarlo.
        respuesta["Cache-Control"] = "private, max-age=3600"
        return respuesta


def _filtrar_por_codigo_o_ci(pasajes, consulta: str):
    """Busca por codigo de pasaje (sin distinguir mayusculas) o por CI del pasajero o de la cuenta."""
    if not consulta:
        return pasajes
    texto = consulta.upper().replace(" ", "")
    return pasajes.filter(Q(codigo_pasaje__iexact=consulta) | Q(cliente_ci=texto) | Q(cliente__ci=texto))


class ReprogramacionesView(RolRequeridoMixin, ListView):
    """Pasajes de quienes perdieron el bus y todavia se pueden reprogramar."""

    roles_permitidos = ["ventanillero", "supervisor", "admin"]
    template_name = "ventas/reprogramaciones.html"
    context_object_name = "pasajes"

    def get_queryset(self):
        self.consulta = self.request.GET.get("q", "").strip()
        return _filtrar_por_codigo_o_ci(pasajes_reprogramables(), self.consulta)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"q": self.consulta, "plazo_dias": PLAZO_REPROGRAMACION.days})
        return context


class ReprogramarView(RolRequeridoMixin, View):
    """Elige el viaje nuevo (?viaje=, ?fecha=) y el asiento, y cobra cargo y diferencia."""

    roles_permitidos = ["ventanillero", "supervisor", "admin"]
    template_name = "ventas/reprogramar.html"

    def _original(self, pk: int) -> Pasaje:
        return get_object_or_404(pasajes_reprogramables(), pk=pk)

    def _viajes(self, request, original: Pasaje):
        texto = (request.GET.get("fecha") or request.POST.get("fecha") or "").strip()
        try:
            fecha = date.fromisoformat(texto) if texto else None
        except ValueError:
            fecha = None
        return fecha, viajes_vendibles(fecha).exclude(pk=original.viaje_id)

    def _render(self, request, original, viajes, fecha, viaje, form):
        precio = None
        if form.is_bound and form.is_valid():
            precio = form.cleaned_data["precio"]
        elif viaje is not None:
            precio = form.initial.get("precio")
        return render(
            request,
            self.template_name,
            {
                "original": original,
                "viajes": viajes,
                "fecha": fecha,
                "viaje_seleccionado": viaje,
                "pisos_asientos": mapa_de_asientos(viaje) if viaje else [],
                "form": form,
                "calculo": calcular_reprogramacion(original, precio) if precio else None,
            },
        )

    def get(self, request, pk: int):
        original = self._original(pk)
        motivo = motivo_no_reprogramable(original)
        if motivo:
            messages.error(request, motivo)
            return redirect("ventas:reprogramaciones")
        fecha, viajes = self._viajes(request, original)
        viaje_id = request.GET.get("viaje", "")
        viaje = viajes.filter(pk=viaje_id).first() if viaje_id.isdigit() else None
        inicial = {"metodo_pago": "efectivo"}
        if viaje and viaje.ruta.precio_base:
            inicial["precio"] = viaje.ruta.precio_base
        return self._render(request, original, viajes, fecha, viaje, ReprogramarForm(initial=inicial))

    def post(self, request, pk: int):
        original = self._original(pk)
        fecha, viajes = self._viajes(request, original)
        viaje = get_object_or_404(viajes, pk=request.POST.get("viaje_id"))
        form = ReprogramarForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            try:
                nuevo = reprogramar_pasaje(
                    original_id=original.pk,
                    viaje=viaje,
                    asiento_viaje_id=datos["asiento_viaje_id"],
                    precio_viaje=datos["precio"],
                    pago=DatosPago(metodo=datos["metodo_pago"], monto=Decimal("0"), referencia=datos["referencia"]),
                    cobrado_por=request.user,
                    facturacion=DatosFacturacion(nit=datos["nit"], razon_social=datos["razon_social"]),
                )
            except ValidationError as error:
                for mensaje in error.messages:
                    form.add_error(None, mensaje)
            else:
                messages.success(
                    request, f"Pasaje {original.codigo_pasaje} reprogramado. Nuevo pasaje {nuevo.codigo_pasaje}."
                )
                return redirect("ventas:boleto", pk=nuevo.pk)
        return self._render(request, original, viajes, fecha, viaje, form)
