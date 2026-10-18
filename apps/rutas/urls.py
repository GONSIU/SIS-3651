from django.urls import path
from . import views

app_name = "rutas"

urlpatterns = [
    path("", views.ListaRutasView.as_view(), name="listado"),
    path("nuevo/", views.NuevaRutaView.as_view(), name="nuevo"),
    path("terminales/nuevo/", views.NuevaTerminalView.as_view(), name="terminal_nuevo"),
    path("<int:ruta_id>/horarios/", views.ListaHorariosView.as_view(), name="horarios"),
    path("<int:ruta_id>/horarios/nuevo/", views.NuevoHorarioView.as_view(), name="horario_nuevo"),
]
