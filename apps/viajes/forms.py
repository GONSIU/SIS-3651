from django import forms
from .models import Viaje
from apps.rutas.models import Ruta, Horario
from apps.flota.models import Bus

SELECT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2.5 bg-white"
INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2.5"


class ViajeForm(forms.ModelForm):
    class Meta:
        model = Viaje
        fields = ["ruta", "horario", "bus", "fecha_salida", "estado"]
        widgets = {
            "ruta": forms.Select(attrs={"class": SELECT_CLASSES}),
            "horario": forms.Select(attrs={"class": SELECT_CLASSES}),
            "bus": forms.Select(attrs={"class": SELECT_CLASSES}),
            "fecha_salida": forms.DateInput(attrs={"class": INPUT_CLASSES, "type": "date"}),
            "estado": forms.Select(attrs={"class": SELECT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ruta"].queryset = Ruta.objects.filter(activa=True).select_related("origen", "destino")
        self.fields["bus"].queryset = Bus.objects.filter(estado="activo")
        self.fields["horario"].queryset = Horario.objects.select_related("ruta")
