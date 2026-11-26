from django.contrib import admin

from .models import Incidencia


@admin.register(Incidencia)
class IncidenciaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "categoria", "titulo", "estado", "reportado_por", "created_at")
    list_filter = ("estado", "categoria")
    search_fields = ("codigo", "titulo", "descripcion")
    readonly_fields = ("codigo", "resuelta_por", "resuelta_en", "created_at", "updated_at")
    raw_id_fields = ("viaje", "bus", "pasaje", "empleado_involucrado", "reportado_por")
