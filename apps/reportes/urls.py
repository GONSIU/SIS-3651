from django.urls import path
from . import views

app_name = "reportes"

urlpatterns = [
    # "listado" se mantiene como nombre porque el sidebar ya apunta a el: es el reporte de ventas.
    path("", views.ReporteVentasView.as_view(), name="listado"),
    path("ventas/pdf/", views.ExportarVentasPdfView.as_view(), name="ventas_pdf"),
    path("ocupacion/", views.ReporteOcupacionView.as_view(), name="ocupacion"),
    path("encomiendas/", views.ReporteEncomiendasView.as_view(), name="encomiendas"),
]
