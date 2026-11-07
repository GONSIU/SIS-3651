from django.contrib import admin
from .models import ComprobanteEncomienda, Encomienda, PagoEncomienda


class PagoEncomiendaInline(admin.TabularInline):
    model = PagoEncomienda
    extra = 0


class ComprobanteEncomiendaInline(admin.StackedInline):
    model = ComprobanteEncomienda
    extra = 0
    max_num = 1
    readonly_fields = ("numero_comprobante",)


@admin.register(Encomienda)
class EncomiendaAdmin(admin.ModelAdmin):
    list_display = (
        "codigo_guia", "viaje", "remitente_nombre", "destinatario_nombre", "peso_kg", "precio_envio", "estado",
    )
    list_filter = ("estado", "fragil")
    search_fields = ("codigo_guia", "remitente_nombre", "remitente_ci", "destinatario_nombre", "destinatario_ci")
    list_select_related = ("viaje__ruta__origen", "viaje__ruta__destino", "viaje__bus")
    readonly_fields = ("codigo_guia", "precio_envio", "registrado_por", "actualizado_por")
    inlines = [PagoEncomiendaInline, ComprobanteEncomiendaInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.registrado_por = request.user
        obj.actualizado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(PagoEncomienda)
class PagoEncomiendaAdmin(admin.ModelAdmin):
    list_display = ("encomienda", "metodo", "monto", "created_at")
    list_filter = ("metodo",)


@admin.register(ComprobanteEncomienda)
class ComprobanteEncomiendaAdmin(admin.ModelAdmin):
    list_display = ("numero_comprobante", "encomienda", "created_at")
    readonly_fields = ("numero_comprobante",)
