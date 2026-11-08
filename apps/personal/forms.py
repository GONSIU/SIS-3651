from django import forms
from .models import Empleado

INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2.5"
SELECT_CLASSES = INPUT_CLASSES + " bg-white"


class EmpleadoForm(forms.ModelForm):
    class Meta:
        model = Empleado
        fields = ["usuario", "cargo", "fecha_ingreso"]
        widgets = {
            "usuario": forms.Select(attrs={"class": SELECT_CLASSES}),
            "cargo": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. Ventanillero"}),
            "fecha_ingreso": forms.DateInput(format="%Y-%m-%d", attrs={"class": INPUT_CLASSES, "type": "date"}),
        }
