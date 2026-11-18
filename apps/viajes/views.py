from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from apps.core.mixins import RolRequeridoMixin
from .forms import RetrasoForm, ViajeForm
from .models import Viaje

# Accion del formulario -> estado al que lleva el viaje.
ACCIONES_CONTROL = {
    "retraso": "retrasado",
    "salida": "en_curso",
    "llegada": "completado",
    "cancelar": "cancelado",
}
# El conductor reporta lo que pasa en su viaje; cancelarlo es una decision de gestion.
ACCIONES_SOLO_GESTION = frozenset({"cancelar"})


def acciones_permitidas(viaje: Viaje, usuario) -> list[str]:
    """Acciones de control que ese usuario puede ejecutar ahora sobre el viaje."""
    return [
        accion
        for accion, estado in ACCIONES_CONTROL.items()
        if estado in viaje.estados_siguientes
        and not (usuario.rol == "conductor" and accion in ACCIONES_SOLO_GESTION)
    ]


class ListaViajesView(RolRequeridoMixin, ListView):
    roles_permitidos = ["supervisor", "admin"]
    model = Viaje
    template_name = "viajes/listado.html"
    context_object_name = "viajes"

    def get_queryset(self):
        # Los conteos de asientos se calculan en la misma consulta (GROUP BY) en lugar
        # de dos count() por viaje: el numero de consultas ya no depende de cuantos
        # viajes haya.
        return (
            Viaje.objects.select_related(
                "ruta__origen", "ruta__destino", "bus", "horario", "conductor__usuario"
            )
            .annotate(
                num_asientos=Count("asientos_viaje"),
                num_vendidos=Count("asientos_viaje", filter=Q(asientos_viaje__estado="vendido")),
            )
            .order_by("-fecha_salida", "horario__hora_salida")[:50]
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for viaje in context["viajes"]:
            viaje.ocupacion_texto = (
                f"{viaje.num_vendidos}/{viaje.num_asientos}" if viaje.num_asientos else "—"
            )
        return context


class NuevoViajeView(RolRequeridoMixin, CreateView):
    roles_permitidos = ["supervisor", "admin"]
    model = Viaje
    form_class = ViajeForm
    template_name = "viajes/nuevo.html"
    success_url = reverse_lazy("viajes:listado")

    def form_valid(self, form):
        form.instance.creado_por = self.request.user
        form.instance.actualizado_por = self.request.user
        response = super().form_valid(form)
        self.object.crear_asientos_desde_bus()
        messages.success(
            self.request,
            f"Viaje programado para el {self.object.fecha_salida} con "
            f"{self.object.asientos_viaje.count()} asientos disponibles.",
        )
        return response
    

class MisViajesView(RolRequeridoMixin, ListView):
    """Viajes asignados al conductor que inicio sesion. ?historial=1 muestra los pasados."""

    roles_permitidos = ["conductor"]
    template_name = "viajes/mis_viajes.html"
    context_object_name = "viajes"

    @property
    def es_historial(self) -> bool:
        return self.request.GET.get("historial") == "1"

    def get_queryset(self):
        hoy = timezone.localdate()
        viajes = Viaje.objects.filter(conductor__usuario=self.request.user).select_related(
            "ruta__origen", "ruta__destino", "bus", "horario"
        )
        if self.es_historial:
            return viajes.filter(fecha_salida__lt=hoy).order_by("-fecha_salida", "-horario__hora_salida")
        return viajes.filter(fecha_salida__gte=hoy).order_by("fecha_salida", "horario__hora_salida")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["es_historial"] = self.es_historial
        return context


def _orden_asiento(pasaje) -> tuple:
    """Ordena por numero de asiento como numero ("2" antes que "10"), no como texto."""
    numero = pasaje.asiento_viaje.asiento.numero
    return (0, int(numero), "") if numero.isdigit() else (1, 0, numero)


class HojaRutaView(RolRequeridoMixin, DetailView):
    """Hoja de ruta imprimible: datos del viaje, pasajeros por asiento y encomiendas.

    El conductor solo ve sus viajes: uno ajeno da 404 (no 403) para no revelar que existe."""

    roles_permitidos = ["conductor", "supervisor", "admin"]
    template_name = "viajes/hoja_ruta.html"
    context_object_name = "viaje"
    # Pasajes que viajan; los cancelados ya no ocupan el asiento.
    ESTADOS_PASAJE_A_BORDO = ("reservado", "pagado", "usado")

    def get_queryset(self):
        viajes = Viaje.objects.select_related(
            "ruta__origen", "ruta__destino", "bus", "horario", "conductor__usuario"
        )
        if self.request.user.rol == "conductor":
            viajes = viajes.filter(conductor__usuario=self.request.user)
        return viajes

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pasajes = sorted(
            self.object.pasajes.filter(estado__in=self.ESTADOS_PASAJE_A_BORDO).select_related(
                "asiento_viaje__asiento", "cliente"
            ),
            key=_orden_asiento,
        )
        # El modelo se toma del manager relacionado para no importar apps.encomiendas:
        # viajes esta por debajo de encomiendas en el grafo de dependencias.
        relacion_encomiendas = self.object.encomiendas
        encomiendas = list(
            relacion_encomiendas.exclude(estado__in=relacion_encomiendas.model.ESTADOS_SIN_CARGA)
            .order_by("codigo_guia")
        )
        context.update(
            {
                "pasajes": pasajes,
                "encomiendas": encomiendas,
                "peso_total_kg": sum((e.peso_kg for e in encomiendas), Decimal("0")),
                "url_volver": reverse(
                    "viajes:mis_viajes" if self.request.user.rol == "conductor" else "viajes:listado"
                ),
                "acciones": acciones_permitidas(self.object, self.request.user),
                "retraso_form": RetrasoForm(),
            }
        )
        return context


class ControlViajeView(RolRequeridoMixin, View):
    """Registra retraso, salida, llegada o cancelacion (solo POST).

    Bloquea el viaje con select_for_update(): si dos personas pulsan a la vez, la
    segunda ve el estado ya cambiado y su transicion se rechaza en vez de pisarla."""

    roles_permitidos = ["conductor", "supervisor", "admin"]
    http_method_names = ["post"]

    def post(self, request, pk: int):
        accion = request.POST.get("accion", "")
        if accion not in ACCIONES_CONTROL:
            messages.error(request, "Accion no valida.")
            return redirect("viajes:hoja_ruta", pk=pk)
        if request.user.rol == "conductor" and accion in ACCIONES_SOLO_GESTION:
            raise PermissionDenied

        with transaction.atomic():
            # of=("self",): bloquea solo la fila del viaje, no las tablas del join.
            viajes = Viaje.objects.select_for_update(of=("self",)).select_related("horario")
            if request.user.rol == "conductor":
                viajes = viajes.filter(conductor__usuario=request.user)
            viaje = get_object_or_404(viajes, pk=pk)
            try:
                mensaje = self._ejecutar(accion, viaje, request)
            except ValidationError as error:
                messages.error(request, " ".join(error.messages))
            else:
                messages.success(request, mensaje)
        return redirect("viajes:hoja_ruta", pk=pk)

    def _ejecutar(self, accion: str, viaje: Viaje, request) -> str:
        usuario = request.user
        if accion == "retraso":
            form = RetrasoForm(request.POST)
            if not form.is_valid():
                raise ValidationError(form.errors["minutos"])
            viaje.marcar_retraso(form.cleaned_data["minutos"], usuario)
            return f"Retraso estimado de {viaje.minutos_retraso} min registrado."
        if accion == "salida":
            viaje.registrar_salida(usuario)
            if viaje.minutos_retraso:
                return f"Salida registrada con {viaje.minutos_retraso} min de retraso."
            return "Salida registrada a tiempo."
        if accion == "llegada":
            viaje.registrar_llegada(usuario)
            return f"Llegada registrada a las {timezone.localtime(viaje.hora_llegada_real):%H:%M}. Viaje completado."
        viaje.cancelar(usuario)
        return "Viaje cancelado."
