from django.contrib import admin
from .models import Pasaje, Pago, Comprobante


class PagoInline(admin.TabularInline):
    model = Pago
    extra = 0


class ComprobanteInline(admin.StackedInline):
    model = Comprobante
    extra = 0
    max_num = 1


@admin.register(Pasaje)
class PasajeAdmin(admin.ModelAdmin):
    list_display = ("codigo_pasaje", "viaje", "nombre_pasajero", "canal", "precio", "estado")
    list_filter = ("estado", "canal")
    search_fields = ("codigo_pasaje", "cliente_nombre", "cliente_ci")
    readonly_fields = ("codigo_pasaje",)
    inlines = [PagoInline, ComprobanteInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.vendido_por = request.user
        obj.actualizado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("pasaje", "metodo", "monto", "created_at")
    list_filter = ("metodo",)


@admin.register(Comprobante)
class ComprobanteAdmin(admin.ModelAdmin):
    list_display = ("numero_comprobante", "pasaje", "tipo", "created_at")
    readonly_fields = ("numero_comprobante",)
