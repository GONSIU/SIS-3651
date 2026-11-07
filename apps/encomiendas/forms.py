from django import forms
from django.utils import timezone

from apps.ventas.models import Pago
from apps.viajes.models import Viaje
from .models import Encomienda

INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-4 py-2.5 font-body-sm text-body-sm"
SELECT_CLASSES = INPUT_CLASSES + " bg-white"


def viajes_para_encomienda():
    """Viajes que todavia pueden recibir carga: no cancelados, no completados, sin salida pasada."""
    return (
        Viaje.objects.filter(fecha_salida__gte=timezone.localdate())
        .exclude(estado__in=["cancelado", "completado"])
        .select_related("ruta__origen", "ruta__destino", "bus", "horario")
        .order_by("fecha_salida", "horario__hora_salida")
    )


class EncomiendaForm(forms.ModelForm):

    metodo_pago = forms.ChoiceField(
        choices=Pago.METODO_CHOICES,
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
    )
    referencia_externa = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Codigo de la transaccion"}),
    )

    class Meta:
        model = Encomienda
        fields = [
            "viaje",
            "remitente_ci",
            "remitente_nombre",
            "remitente_telefono",
            "destinatario_ci",
            "destinatario_nombre",
            "destinatario_telefono",
            "descripcion_contenido",
            "peso_kg",
            "valor_declarado",
            "fragil",
            "foto_paquete",
        ]
        widgets = {
            "viaje": forms.Select(attrs={"class": SELECT_CLASSES}),
            "remitente_ci": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Numero de documento"}),
            "remitente_nombre": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Nombre completo"}),
            "remitente_telefono": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 70123456"}),
            "destinatario_ci": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Numero de documento"}),
            "destinatario_nombre": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Nombre completo"}),
            "destinatario_telefono": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 70123456"}),
            "descripcion_contenido": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Ej. Documentos, ropa, repuestos"}
            ),
            "peso_kg": forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "0.00", "step": "0.01"}),
            "valor_declarado": forms.NumberInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "0.00", "step": "0.01"}
            ),
            "fragil": forms.CheckboxInput(attrs={"class": "w-4 h-4"}),
            "foto_paquete": forms.ClearableFileInput(attrs={"class": INPUT_CLASSES, "accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["viaje"].queryset = viajes_para_encomienda()
        self.fields["viaje"].empty_label = "Seleccione un viaje"

    def clean(self):
        cleaned_data = super().clean()
        metodo = cleaned_data.get("metodo_pago")
        if metodo and metodo != "efectivo" and not cleaned_data.get("referencia_externa"):
            self.add_error("referencia_externa", "Este metodo de pago necesita una referencia.")
        return cleaned_data
