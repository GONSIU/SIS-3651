from django.urls import path
from . import views

app_name = "viajes"

urlpatterns = [
    path("", views.ListaViajesView.as_view(), name="listado"),
    path("nuevo/", views.NuevoViajeView.as_view(), name="nuevo"),
    path("mis-viajes/", views.MisViajesView.as_view(), name="mis_viajes"),
    path("<int:pk>/hoja-ruta/", views.HojaRutaView.as_view(), name="hoja_ruta"),
    path("<int:pk>/control/", views.ControlViajeView.as_view(), name="control"),
    path("<int:pk>/abordaje/", views.AbordajeView.as_view(), name="abordaje"),
]
