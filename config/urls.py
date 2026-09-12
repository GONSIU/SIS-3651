from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cuentas/", include("apps.usuarios.urls")),
    path("rutas/", include("apps.rutas.urls")),
    path("flota/", include("apps.flota.urls")),
    path("viajes/", include("apps.viajes.urls")),
    path("ventas/", include("apps.ventas.urls")),
    path("encomiendas/", include("apps.encomiendas.urls")),
    path("incidencias/", include("apps.incidencias.urls")),
    path("reportes/", include("apps.reportes.urls")),
    path("personal/", include("apps.personal.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
