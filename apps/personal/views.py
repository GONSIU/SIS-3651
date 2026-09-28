from django.views.generic import TemplateView

# Vistas de la app "personal"

class ListaPersonalView(TemplateView):
    template_name="personal/listado.html"
