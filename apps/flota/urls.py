from django.urls import path
from . import views

app_name = "flota"

urlpatterns = [
    path("", views.ListaFlotaView.as_view(), name="listado"),
    path("nuevo/", views.NuevoBusView.as_view(), name="nuevo"),
]
