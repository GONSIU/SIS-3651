# Rutas de la app "core": raiz del sitio y dashboard general.
from django.urls import path
from . import views, views_notificaciones

app_name = "core"

urlpatterns = [
    path("", views.LandingView.as_view(), name="root"),
    path("salidas/", views.SalidasView.as_view(), name="salidas"),
    path("sobre-nosotros/", views.NosotrosView.as_view(), name="nosotros"),
    path("dashboard/", views.IndexView.as_view(), name="index"),
    path("buscar/", views.BuscarView.as_view(), name="buscar"),
    path("notificaciones/", views_notificaciones.BandejaNotificacionesView.as_view(), name="notificaciones"),
    path(
        "notificaciones/leidas/",
        views_notificaciones.MarcarTodasLeidasView.as_view(),
        name="notificaciones_leidas",
    ),
    path(
        "notificaciones/<int:pk>/",
        views_notificaciones.DetalleNotificacionView.as_view(),
        name="notificacion",
    ),
    path(
        "notificaciones/<int:pk>/eliminar/",
        views_notificaciones.EliminarNotificacionView.as_view(),
        name="notificacion_eliminar",
    ),
]
