from django import forms
from .models import Bus

INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2.5"
SELECT_CLASSES = INPUT_CLASSES + " bg-white"


class BusForm(forms.ModelForm):
    class Meta:
        model = Bus
        fields = ["placa", "nombre_tipo", "capacidad_pasajeros", "pisos", "capacidad_carga_kg", "estado"]
        widgets = {
            "placa": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 1234-ABC"}),
            "nombre_tipo": forms.Select(
                choices=[("Leito", "Leito"), ("Cama", "Cama"), ("Semicama", "Semicama")],
                attrs={"class": SELECT_CLASSES},
            ),
            "capacidad_pasajeros": forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 32"}),
            "pisos": forms.Select(attrs={"class": SELECT_CLASSES}),
            "capacidad_carga_kg": forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 1200"}),
            "estado": forms.Select(attrs={"class": SELECT_CLASSES}),
        }
