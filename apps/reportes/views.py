from django.views.generic import TemplateView

# Vistas de la app "reportes"
class ListaReportesView(TemplateView):
    template_name="reportes/listado.html"
