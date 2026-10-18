# Rutas de la app "core": raiz del sitio y dashboard general.
from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.root_redirect, name="root"),
    path("dashboard/", views.IndexView.as_view(), name="index"),
]
