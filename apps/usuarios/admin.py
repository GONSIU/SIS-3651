from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "email", "rol","terminal_asignado", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("Información adicional", {"fields": ("rol", "telefono", "ci", "terminal_asignado")}),
    )
