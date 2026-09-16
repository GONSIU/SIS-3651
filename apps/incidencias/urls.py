from django.urls import path
from . import views

app_name = "incidencias"

urlpatterns = [
    path("", views.ListaIncidenciasView.as_view(), name="listado"),
    path("nueva/", views.NuevaIncidenciaView.as_view(), name="nueva"),
]