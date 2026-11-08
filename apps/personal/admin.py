from django.contrib import admin
from .models import Empleado


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "cargo", "terminal", "fecha_ingreso")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name", "cargo")
    list_select_related = ("usuario__terminal_asignado",)
