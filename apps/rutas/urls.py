from django.urls import path
from . import views

app_name = "rutas"

urlpatterns = [
    path("", views.ListaRutasView.as_view(), name="listado"),
    path("nuevo/", views.NuevaRutaView.as_view(), name="nuevo"),
    path("terminales/nuevo/", views.NuevaTerminalView.as_view(), name="terminal_nuevo"),
    path("<int:ruta_id>/horarios/", views.ListaHorariosView.as_view(), name="horarios"),
    path("<int:ruta_id>/horarios/nuevo/", views.NuevoHorarioView.as_view(), name="horario_nuevo"),
    path("<int:pk>/editar/", views.EditarRutaView.as_view(), name="editar"),
    path("<int:pk>/eliminar/", views.EliminarRutaView.as_view(), name="eliminar"),
    path("<int:pk>/activar/", views.CambiarActivaRutaView.as_view(), name="activar"),
    path("horarios/<int:pk>/editar/", views.EditarHorarioView.as_view(), name="horario_editar"),
    path("horarios/<int:pk>/eliminar/", views.EliminarHorarioView.as_view(), name="horario_eliminar"),
    path("horarios/<int:pk>/activar/", views.CambiarActivoHorarioView.as_view(), name="horario_activar"),
]
