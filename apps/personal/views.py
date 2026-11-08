from datetime import date

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView

from apps.ventas.models import Pasaje
from .forms import EmpleadoForm
from .models import Empleado


class ListaEmpleadosView(ListView):
    model = Empleado
    template_name = "personal/listado.html"
    context_object_name = "empleados"

    def get_queryset(self):
        return Empleado.objects.select_related("usuario__terminal_asignado")


class NuevoEmpleadoView(CreateView):
    model = Empleado
    form_class = EmpleadoForm
    template_name = "personal/nuevo.html"
    success_url = reverse_lazy("personal:listado")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Empleado {self.object} registrado.")
        return response


class DesempenoVentanillaView(TemplateView):
    """Ventas por vendedor en un dia, calculadas en vivo desde Pasaje (sin tabla propia)."""

    template_name = "personal/desempeno.html"

    def _fecha(self) -> tuple[date, bool]:
        """Devuelve la fecha pedida en ?fecha=YYYY-MM-DD y si era valida; si no, hoy."""
        texto = self.request.GET.get("fecha", "")
        if not texto:
            return timezone.localdate(), True
        try:
            return date.fromisoformat(texto), True
        except ValueError:
            return timezone.localdate(), False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fecha, fecha_valida = self._fecha()

        resumen = (
            Pasaje.objects.filter(created_at__date=fecha, vendido_por__isnull=False)
            .values("vendido_por")
            .annotate(ventas_realizadas=Count("id"), monto_total_vendido=Sum("precio"))
            .order_by("-monto_total_vendido")
        )
        vendedores = get_user_model().objects.select_related("empleado", "terminal_asignado").in_bulk(
            [fila["vendido_por"] for fila in resumen]
        )

        filas = []
        for fila in resumen:
            usuario = vendedores[fila["vendido_por"]]
            empleado = getattr(usuario, "empleado", None)
            filas.append(
                {
                    "nombre": usuario.get_full_name() or usuario.username,
                    "username": usuario.username,
                    "cargo": empleado.cargo if empleado else None,
                    "terminal": usuario.terminal_asignado,
                    "ventas_realizadas": fila["ventas_realizadas"],
                    "monto_total_vendido": fila["monto_total_vendido"],
                }
            )

        context.update(
            {
                "fecha": fecha,
                "fecha_valida": fecha_valida,
                "filas": filas,
                "total_ventas": sum(f["ventas_realizadas"] for f in filas),
                "total_monto": sum(f["monto_total_vendido"] for f in filas),
            }
        )
        return context
