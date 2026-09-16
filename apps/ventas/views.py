from django.views.generic import TemplateView


class NuevaVentaView(TemplateView):
    """Maqueta visual — sin lógica de negocio todavía."""
    template_name = "ventas/nueva_venta.html"