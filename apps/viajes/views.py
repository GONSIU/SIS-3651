from django.views.generic import TemplateView


class ListaViajesView(TemplateView):
    """Maqueta visual — sin lógica de negocio todavía."""
    template_name = "viajes/listado.html"


class NuevoViajeView(TemplateView):
    """Maqueta visual — sin lógica de negocio todavía."""
    template_name = "viajes/nuevo.html"
