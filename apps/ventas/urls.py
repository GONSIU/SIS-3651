from django.urls import path
from . import views, views_publicas

app_name = "ventas"

urlpatterns = [
    path("nueva/", views.NuevaVentaView.as_view(), name="nueva_venta"),
    path("boleto/<int:pk>/", views.VerBoletoView.as_view(), name="boleto"),
    # Publicas (VISTAS_PUBLICAS en apps/core/middleware.py)
    path("viajes/", views_publicas.BuscarViajesView.as_view(), name="buscar_viajes"),
    path("viajes/<int:pk>/", views_publicas.ViajePublicoView.as_view(), name="viaje_publico"),
    path("viajes/<int:pk>/mapa/", views_publicas.MapaPublicoView.as_view(), name="mapa_publico"),
]
