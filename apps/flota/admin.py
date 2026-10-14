from django.contrib import admin
from .models import Bus, Asiento


class AsientoInline(admin.TabularInline):
    model = Asiento
    extra = 0


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ("placa", "nombre_tipo", "capacidad_pasajeros", "estado")
    list_filter = ("estado", "nombre_tipo")
    search_fields = ("placa",)
    inlines = [AsientoInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            obj.crear_asientos()


@admin.register(Asiento)
class AsientoAdmin(admin.ModelAdmin):
    list_display = ("bus", "numero", "piso", "fila", "columna")
    list_filter = ("bus", "piso")
