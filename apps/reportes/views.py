from django.views.generic import TemplateView

from apps.core.mixins import RolRequeridoMixin

# Vistas de la app "reportes"
class ListaReportesView(RolRequeridoMixin, TemplateView):
    roles_permitidos = ["supervisor", "admin"]
    template_name="reportes/listado.html"
