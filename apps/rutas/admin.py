from django.contrib import admin
from .models import Terminal, Ruta, Horario

# Registra aquí los modelos de la app "rutas"

@admin.register(Terminal)
class TerminalAdmin(admin.ModelAdmin):
    list_display = ("nombre", "ciudad")
    search_fields = ("nombre", "ciudad")
 
 
@admin.register(Ruta)
class RutaAdmin(admin.ModelAdmin):
    list_display = ("origen", "destino", "distancia_km", "activa")
    list_filter = ("activa",)
 
 
@admin.register(Horario)
class HorarioAdmin(admin.ModelAdmin):
    list_display = ("ruta", "hora_salida", "dias_semana")
 