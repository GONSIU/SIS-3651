from django.contrib import admin
from .models import Viaje, AsientoViaje

# Registra aquí los modelos de la app "viajes"

class AsientoViajeInline(admin.TabularInline):
    model = AsientoViaje
    extra = 0
    readonly_fields = ("asiento",)
 
 
@admin.register(Viaje)
class ViajeAdmin(admin.ModelAdmin):
    list_display = ("ruta", "fecha_salida", "horario", "bus", "estado", "minutos_retraso")
    list_filter = ("estado", "fecha_salida")
    inlines = [AsientoViajeInline]
 
    def save_model(self, request, obj, form, change):
        if not change:
            obj.creado_por = request.user
        obj.actualizado_por = request.user
        super().save_model(request, obj, form, change)
        if not change:
            obj.crear_asientos_desde_bus()
 
 
@admin.register(AsientoViaje)
class AsientoViajeAdmin(admin.ModelAdmin):
    list_display = ("viaje", "asiento", "estado")
    list_filter = ("estado",)