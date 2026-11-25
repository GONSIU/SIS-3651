from django import forms
from django.contrib.auth import get_user_model

from .models import Empleado

INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2.5"
SELECT_CLASSES = INPUT_CLASSES + " bg-white"


def usuarios_sin_ficha():
    """Personal activo que todavia no tiene ficha laboral.

    Los clientes no son empleados, y un usuario con ficha ya no puede tener otra
    (OneToOne). La cuenta se crea antes en Usuarios."""
    return (
        get_user_model()
        .objects.filter(is_active=True, empleado__isnull=True)
        .exclude(rol="cliente")
        .order_by("first_name", "last_name", "username")
    )


class UsuarioSelect(forms.Select):
    """Cada opcion lleva data-rol para que el template filtre los cargos compatibles."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        opcion = super().create_option(name, value, label, selected, index, subindex, attrs)
        usuario = getattr(value, "instance", None)
        if usuario is not None:
            opcion["attrs"]["data-rol"] = usuario.rol
        return opcion


class CargoSelect(forms.Select):
    """Cada cargo lleva data-roles: los roles de usuario que lo admiten."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        opcion = super().create_option(name, value, label, selected, index, subindex, attrs)
        roles = [rol for rol, cargos in Empleado.CARGOS_POR_ROL.items() if value in cargos]
        if roles:
            opcion["attrs"]["data-roles"] = ",".join(roles)
        return opcion


class UsuarioChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj) -> str:
        nombre = obj.get_full_name() or obj.username
        return f"{nombre} ({obj.username}) - rol {obj.get_rol_display()}"


class EmpleadoForm(forms.ModelForm):
    # Declarado en la clase para filtrar el queryset sin sobrescribir __init__.
    # Django copia el campo y vuelve a evaluar el queryset en cada formulario, asi que
    # la lista siempre esta al dia.
    usuario = UsuarioChoiceField(
        queryset=usuarios_sin_ficha(),
        label="Usuario",
        empty_label="Selecciona un usuario",
        error_messages={
            "invalid_choice": "Elige un usuario de personal activo que aun no tenga ficha."
        },
        widget=UsuarioSelect(attrs={"class": SELECT_CLASSES}),
    )

    class Meta:
        model = Empleado
        fields = ["usuario", "cargo", "fecha_ingreso"]
        widgets = {
            "cargo": CargoSelect(attrs={"class": SELECT_CLASSES}),
            "fecha_ingreso": forms.DateInput(format="%Y-%m-%d", attrs={"class": INPUT_CLASSES, "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Sin default en el modelo, Django pone "---------" como primera opcion.
        self.fields["cargo"].choices = [("", "Selecciona un cargo"), *Empleado.CARGO_CHOICES]
