# Rutas de la app "core": raiz del sitio y dashboard general.
from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.LandingView.as_view(), name="root"),
    path("salidas/", views.SalidasView.as_view(), name="salidas"),
    path("sobre-nosotros/", views.NosotrosView.as_view(), name="nosotros"),
    path("dashboard/", views.IndexView.as_view(), name="index"),
    path("buscar/", views.BuscarView.as_view(), name="buscar"),
]
