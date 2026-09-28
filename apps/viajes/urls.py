from django.urls import path
from . import views

app_name = "viajes"

urlpatterns = [
    path("", views.ListaViajesView.as_view(), name="listado"),
    path("nuevo/", views.NuevoViajeView.as_view(), name="nuevo"),
]
