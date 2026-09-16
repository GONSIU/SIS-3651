from django.views.generic import TemplateView


class ListaIncidenciasView(TemplateView):
    """Maqueta visual — sin logica de negocio todavia."""
    template_name = "incidencias/listado.html"


class NuevaIncidenciaView(TemplateView):
    """Maqueta visual — sin lógica de negocio todavia."""
    template_name = "incidencias/nueva.html"