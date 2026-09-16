from django.urls import path
from . import views

app_name = "encomiendas"

urlpatterns = [
    path("", views.ListaEncomiendasView.as_view(), name="listado"),
    path("nueva/", views.NuevaEncomiendaView.as_view(), name="nueva"),
]