from decimal import Decimal

from django import forms
from apps.core.validators import (
    normalizar_ci,
    normalizar_espacios,
    normalizar_telefono,
    validar_ci,
    validar_nombre_persona,
    validar_telefono,
)
from .models import Pago

INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-4 py-2.5 font-body-sm text-body-sm"
SELECT_CLASSES = INPUT_CLASSES + " bg-white"


class VentaForm(forms.Form):
    asiento_viaje_id = forms.IntegerField(widget=forms.HiddenInput)
    cliente_nombre = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ingrese el nombre del pasajero"}),
    )
    cliente_ci = forms.CharField(
        max_length=12,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Número de documento"}),
    )
    telefono = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "+591"}),
    )
    precio = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 120.00", "step": "0.01"}),
    )
    metodo_pago = forms.ChoiceField(
        choices=Pago.METODO_CHOICES,
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
    )
    referencia_externa = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Codigo de la transaccion"}),
    )

    # Los validadores se llaman aqui y no con validators=[...] porque estos corren
    # antes de clean_<campo>: rechazarian "7123-4567" sin darle ocasion de normalizarse.
    def clean_cliente_nombre(self) -> str:
        valor = normalizar_espacios(self.cleaned_data["cliente_nombre"])
        validar_nombre_persona(valor)
        return valor

    def clean_cliente_ci(self) -> str:
        valor = normalizar_ci(self.cleaned_data["cliente_ci"])
        if valor:
            validar_ci(valor)
        return valor

    def clean_telefono(self) -> str:
        valor = normalizar_telefono(self.cleaned_data["telefono"])
        if valor:
            validar_telefono(valor)
        return valor

    def clean(self):
        cleaned_data = super().clean()
        metodo = cleaned_data.get("metodo_pago")
        if metodo and metodo != "efectivo" and not cleaned_data.get("referencia_externa"):
            self.add_error("referencia_externa", "Este metodo de pago necesita una referencia.")
        return cleaned_data
