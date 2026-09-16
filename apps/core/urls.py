# La app "core" no expone rutas propias; contiene utilidades compartidas.
from django.urls import path
from . import views

urlpatterns = [
    path("", views.root_redirect, name="root"),
]
