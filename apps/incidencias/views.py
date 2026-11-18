from django.views.generic import TemplateView

from apps.core.mixins import RolRequeridoMixin


class ListaIncidenciasView(RolRequeridoMixin, TemplateView):
    """Maqueta visual — sin logica de negocio todavia."""
    roles_permitidos = ["supervisor", "admin"]
    template_name = "incidencias/listado.html"


class NuevaIncidenciaView(RolRequeridoMixin, TemplateView):
    """Maqueta visual — sin lógica de negocio todavia."""
    roles_permitidos = ["supervisor", "admin"]
    template_name = "incidencias/nueva.html"