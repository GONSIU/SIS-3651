from django import forms
from .models import Pago

INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-4 py-2.5 font-body-sm text-body-sm"
SELECT_CLASSES = INPUT_CLASSES + " bg-white"


class VentaForm(forms.Form):
    asiento_viaje_id = forms.IntegerField(widget=forms.HiddenInput)
    cliente_nombre = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ingrese el nombre del pasajero"}),
    )
    cliente_ci = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Número de documento"}),
    )
    telefono = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "+591"}),
    )
    precio = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 120.00", "step": "0.01"}),
    )
    metodo_pago = forms.ChoiceField(
        choices=Pago.METODO_CHOICES,
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
    )