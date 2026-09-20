from django.views.generic import TemplateView

# Vistas de la app "flota"
class ListaFlotaView(TemplateView):
    template_name="flota/listado.html"
    
class NuevoBusView(TemplateView):
    template_name = "flota/nuevo.html"