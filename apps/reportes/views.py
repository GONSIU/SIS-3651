from urllib.parse import urlencode

from django.http import HttpResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import RolRequeridoMixin

from . import services
from .forms import ReporteFiltroForm
from .pdf import pdf_reporte_ventas

ROLES_REPORTES = ["supervisor", "admin"]


class FiltroReporteMixin:
    """Lee los filtros del querystring y deja en el contexto el formulario, el periodo,
    la ruta/terminal elegidas y las URLs de las pestanas Diario/Semanal/Mensual (que
    conservan la ruta y la terminal)."""

    def filtros_reporte(self) -> tuple[ReporteFiltroForm, services.Periodo, dict]:
        form = ReporteFiltroForm(self.request.GET or None)
        periodo = form.periodo_elegido(timezone.localdate())
        return form, periodo, form.filtros()

    def contexto_filtros(self, form, periodo, filtros) -> dict:
        conservar = {k: v.pk for k, v in filtros.items() if v is not None}
        pestanas = [
            {
                "tipo": tipo,
                "etiqueta": tipo.capitalize(),
                "url": "?" + urlencode({"periodo": tipo, **conservar}),
                "activa": periodo.tipo == tipo,
            }
            for tipo in services.TIPOS_PERIODO
        ]
        return {"form": form, "periodo": periodo, "filtros": filtros, "pestanas": pestanas}


class ReporteVentasView(RolRequeridoMixin, FiltroReporteMixin, TemplateView):
    """Reporte de ventas: tarjetas de resumen, ingresos por ruta y detalle diario."""

    roles_permitidos = ROLES_REPORTES
    template_name = "reportes/listado.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form, periodo, filtros = self.filtros_reporte()
        context.update(self.contexto_filtros(form, periodo, filtros))
        context["reporte"] = services.reporte_ventas(periodo, **filtros)
        # El PDF recibe exactamente los mismos filtros que la pantalla.
        context["querystring"] = self.request.GET.urlencode()
        return context


class ExportarVentasPdfView(RolRequeridoMixin, FiltroReporteMixin, View):
    roles_permitidos = ROLES_REPORTES

    def get(self, request, *args, **kwargs):
        _form, periodo, filtros = self.filtros_reporte()
        reporte = services.reporte_ventas(periodo, **filtros)
        partes = [f"Ruta: {filtros['ruta']}" if filtros["ruta"] else "Todas las rutas"]
        if filtros["terminal"]:
            partes.append(f"Terminal de origen: {filtros['terminal']}")
        contenido = pdf_reporte_ventas(reporte, ". ".join(partes) + ".")
        respuesta = HttpResponse(contenido, content_type="application/pdf")
        nombre = f"reporte-ventas-{periodo.desde:%Y%m%d}-{periodo.hasta:%Y%m%d}.pdf"
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return respuesta


class ReporteOcupacionView(RolRequeridoMixin, FiltroReporteMixin, TemplateView):
    """Ocupacion de asientos por viaje (vendidos / asientos del viaje)."""

    roles_permitidos = ROLES_REPORTES
    template_name = "reportes/ocupacion.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form, periodo, filtros = self.filtros_reporte()
        context.update(self.contexto_filtros(form, periodo, filtros))
        context["reporte"] = services.reporte_ocupacion(periodo, **filtros)
        return context


class ReporteEncomiendasView(RolRequeridoMixin, FiltroReporteMixin, TemplateView):
    """Encomiendas registradas en el periodo, por estado."""

    roles_permitidos = ROLES_REPORTES
    template_name = "reportes/encomiendas.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form, periodo, filtros = self.filtros_reporte()
        context.update(self.contexto_filtros(form, periodo, filtros))
        context["reporte"] = services.reporte_encomiendas(periodo, **filtros)
        return context
