from django.urls import path
from . import views

app_name = "personal"

urlpatterns = [
    path("", views.ListaEmpleadosView.as_view(), name="listado"),
    path("nuevo/", views.NuevoEmpleadoView.as_view(), name="nuevo"),
    path("desempeno/", views.DesempenoVentanillaView.as_view(), name="desempeno"),
]
