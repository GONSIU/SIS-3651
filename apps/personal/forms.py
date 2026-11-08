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


class EmpleadoForm(forms.ModelForm):
    # Declarado en la clase para filtrar el queryset sin sobrescribir __init__.
    # Django copia el campo y vuelve a evaluar el queryset en cada formulario, asi que
    # la lista siempre esta al dia.
    usuario = forms.ModelChoiceField(
        queryset=usuarios_sin_ficha(),
        label="Usuario",
        empty_label="Selecciona un usuario",
        error_messages={
            "invalid_choice": "Elige un usuario de personal activo que aun no tenga ficha."
        },
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
    )

    class Meta:
        model = Empleado
        fields = ["usuario", "cargo", "fecha_ingreso"]
        widgets = {
            "cargo": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. Ventanillero"}),
            "fecha_ingreso": forms.DateInput(format="%Y-%m-%d", attrs={"class": INPUT_CLASSES, "type": "date"}),
        }
