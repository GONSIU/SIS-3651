from django.urls import path
from . import views

app_name = "ventas"

urlpatterns = [
    path("nueva/", views.NuevaVentaView.as_view(), name="nueva_venta"),
]