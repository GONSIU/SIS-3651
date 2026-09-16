from django.views.generic import TemplateView


class ListaEncomiendasView(TemplateView):
    """Maqueta visual — sin lógica de negocio todavia."""
    template_name = "encomiendas/listado.html"


class NuevaEncomiendaView(TemplateView):
    """Maqueta visual — sin lógica de negocio todavia."""
    template_name = "encomiendas/nueva.html"