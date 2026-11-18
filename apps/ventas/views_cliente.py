"""Vistas del cliente con sesion: reservar online, ver sus pasajes y cancelar reservas.

Solo rol cliente: el personal vende desde la ventanilla."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import RolRequeridoMixin
from .forms import ReservaForm
from .models import Pasaje
from .services import (
    CIERRE_RESERVA_ONLINE,
    DatosFacturacion,
    DatosPago,
    DatosPasajero,
    cancelar_reserva,
    liberar_reservas_vencidas,
    monto_minimo_anticipo,
    registrar_reserva,
    viajes_reservables_online,
)

# Errores del servicio que corresponden a un campo del formulario.
CAMPOS_DEL_SERVICIO = {"cliente_nombre", "monto", "metodo"}


class ReservarView(RolRequeridoMixin, View):
    """/ventas/viajes/<pk>/reservar/?asiento=<id>: datos del pasajero, pago y condiciones."""

    roles_permitidos = ["cliente"]
    template_name = "ventas/cliente/reservar.html"

    def _cargar_viaje(self, pk: int) -> None:
        """Se llama al inicio de get/post, que solo corren si el rol ya fue autorizado:
        un visitante sin permiso recibe 403 sin que se consulte el viaje."""
        self.viaje = get_object_or_404(viajes_reservables_online(), pk=pk)
        self.precio = self.viaje.ruta.precio_base
        self.monto_minimo = monto_minimo_anticipo(self.precio)

    def _asiento(self, request):
        """El asiento elegido, solo si sigue libre. El servicio lo vuelve a comprobar con bloqueo."""
        asiento_id = request.GET.get("asiento") or request.POST.get("asiento")
        if not str(asiento_id).isdigit():
            return None
        return (
            self.viaje.asientos_viaje.select_related("asiento")
            .filter(pk=asiento_id, estado="disponible")
            .first()
        )

    def _volver_al_mapa(self, request, mensaje: str):
        messages.error(request, mensaje)
        return redirect("ventas:viaje_publico", pk=self.viaje.pk)

    def _form(self, data=None) -> ReservaForm:
        usuario = self.request.user
        inicial = {
            "cliente_nombre": usuario.get_full_name(),
            "cliente_ci": usuario.ci or "",
            "cliente_telefono": usuario.telefono,
            "monto": self.monto_minimo,
        }
        return ReservaForm(data, initial=inicial, precio=self.precio, monto_minimo=self.monto_minimo)

    def _render(self, request, form, asiento):
        return render(
            request,
            self.template_name,
            {
                "viaje": self.viaje,
                "asiento": asiento,
                "form": form,
                "precio": self.precio,
                "monto_minimo": self.monto_minimo,
                "reservado_hasta": self.viaje.salida_programada - CIERRE_RESERVA_ONLINE,
                "cuenta": request.user,
            },
        )

    def get(self, request, pk: int):
        self._cargar_viaje(pk)
        asiento = self._asiento(request)
        if asiento is None:
            return self._volver_al_mapa(request, "Elige un asiento libre en el mapa.")
        return self._render(request, self._form(), asiento)

    def post(self, request, pk: int):
        self._cargar_viaje(pk)
        asiento = self._asiento(request)
        if asiento is None:
            return self._volver_al_mapa(request, "Ese asiento ya no esta disponible. Elige otro.")
        form = self._form(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            try:
                pasaje = registrar_reserva(
                    viaje=self.viaje,
                    asiento_viaje_id=asiento.pk,
                    comprador=request.user,
                    pasajero=DatosPasajero(
                        nombre=datos["cliente_nombre"], ci=datos["cliente_ci"], telefono=datos["cliente_telefono"]
                    ),
                    pago=DatosPago(metodo=datos["metodo"], monto=datos["monto"], referencia=datos["referencia"]),
                    facturacion=DatosFacturacion(nit=datos["nit"], razon_social=datos["razon_social"]),
                )
            except ValidationError as error:
                self._agregar_errores(form, error)
            else:
                if pasaje.estado == "pagado":
                    messages.success(request, f"Pasaje {pasaje.codigo_pasaje} pagado. Este es tu boleto.")
                else:
                    messages.success(
                        request,
                        f"Reserva {pasaje.codigo_pasaje} registrada. Paga el saldo de Bs {pasaje.saldo} en ventanilla "
                        f"antes del {pasaje.reservado_hasta:%d/%m/%Y %H:%M}.",
                    )
                return redirect("ventas:boleto", pk=pasaje.pk)
        return self._render(request, form, asiento)

    @staticmethod
    def _agregar_errores(form, error: ValidationError) -> None:
        if not hasattr(error, "error_dict"):
            for mensaje in error.messages:
                form.add_error(None, mensaje)
            return
        for campo, mensajes in error.message_dict.items():
            destino = campo if campo in CAMPOS_DEL_SERVICIO else None
            for mensaje in mensajes:
                form.add_error(destino, mensaje)


class MisPasajesView(RolRequeridoMixin, ListView):
    """Pasajes de la cuenta: reservas online y compras en ventanilla con su CI."""

    roles_permitidos = ["cliente"]
    template_name = "ventas/cliente/mis_pasajes.html"
    context_object_name = "pasajes"

    def get_queryset(self):
        liberar_reservas_vencidas()
        return (
            Pasaje.objects.filter(cliente=self.request.user)
            .select_related("viaje__ruta__origen", "viaje__ruta__destino", "viaje__horario", "asiento_viaje__asiento")
            .prefetch_related("pagos")
            .order_by("-viaje__fecha_salida", "-created_at")
        )


class CancelarReservaView(RolRequeridoMixin, View):
    """Cancela una reserva propia pendiente de pago (solo POST). El anticipo se pierde."""

    roles_permitidos = ["cliente"]
    http_method_names = ["post"]

    def post(self, request, pk: int):
        pasaje = get_object_or_404(Pasaje, pk=pk, cliente=request.user)
        try:
            cancelar_reserva(pasaje, request.user)
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
        else:
            messages.success(request, f"Reserva {pasaje.codigo_pasaje} cancelada. El asiento quedo libre.")
        return redirect(reverse("ventas:mis_pasajes"))
