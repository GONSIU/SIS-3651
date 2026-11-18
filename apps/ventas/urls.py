from django.urls import path
from . import views, views_cliente, views_publicas

app_name = "ventas"

urlpatterns = [
    path("nueva/", views.NuevaVentaView.as_view(), name="nueva_venta"),
    path("boleto/<int:pk>/", views.VerBoletoView.as_view(), name="boleto"),
    path("reservas/", views.ReservasPendientesView.as_view(), name="reservas_pendientes"),
    path("reservas/<int:pk>/cobrar/", views.CobrarSaldoView.as_view(), name="cobrar_saldo"),
    path("pasajero/", views.BuscarPasajeroView.as_view(), name="buscar_pasajero"),
    # Publicas (VISTAS_PUBLICAS en apps/core/middleware.py)
    path("viajes/", views_publicas.BuscarViajesView.as_view(), name="buscar_viajes"),
    path("viajes/<int:pk>/", views_publicas.ViajePublicoView.as_view(), name="viaje_publico"),
    path("viajes/<int:pk>/mapa/", views_publicas.MapaPublicoView.as_view(), name="mapa_publico"),
    # Cliente con sesion
    path("viajes/<int:pk>/reservar/", views_cliente.ReservarView.as_view(), name="reservar"),
    path("mis-pasajes/", views_cliente.MisPasajesView.as_view(), name="mis_pasajes"),
    path("mis-pasajes/<int:pk>/cancelar/", views_cliente.CancelarReservaView.as_view(), name="cancelar_reserva"),
]
