from django.urls import path
from . import views

app_name = "incidencias"

urlpatterns = [
    path("", views.ListaIncidenciasView.as_view(), name="listado"),
    path("nueva/", views.NuevaIncidenciaView.as_view(), name="nueva"),
    path("<int:pk>/", views.DetalleIncidenciaView.as_view(), name="detalle"),
    path("<int:pk>/estado/", views.CambiarEstadoIncidenciaView.as_view(), name="cambiar_estado"),
    path("reclamos/", views.MisReclamosView.as_view(), name="mis_reclamos"),
    path("reclamos/nuevo/", views.NuevoReclamoView.as_view(), name="nuevo_reclamo"),
]
