from django import forms
from .models import Viaje
from apps.flota.models import Bus
from apps.personal.models import Empleado
from apps.rutas.models import Ruta, Horario

SELECT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2.5 bg-white"
INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2.5"


def conductores_disponibles():
    """Empleados con rol conductor y cuenta activa: los unicos que pueden asignarse."""
    return (
        Empleado.objects.filter(usuario__rol="conductor", usuario__is_active=True)
        .select_related("usuario")
        .order_by("usuario__first_name", "usuario__last_name", "usuario__username")
    )


class ViajeForm(forms.ModelForm):
    class Meta:
        model = Viaje
        fields = ["ruta", "horario", "bus", "conductor", "fecha_salida", "estado"]
        help_texts = {
            "conductor": "Opcional. Solo aparecen conductores activos con ficha en Personal.",
        }
        widgets = {
            "ruta": forms.Select(attrs={"class": SELECT_CLASSES}),
            "horario": forms.Select(attrs={"class": SELECT_CLASSES}),
            "bus": forms.Select(attrs={"class": SELECT_CLASSES}),
            "conductor": forms.Select(attrs={"class": SELECT_CLASSES}),
            "fecha_salida": forms.DateInput(attrs={"class": INPUT_CLASSES, "type": "date"}),
            "estado": forms.Select(attrs={"class": SELECT_CLASSES}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ruta"].queryset = Ruta.objects.filter(activa=True).select_related("origen", "destino")
        self.fields["bus"].queryset = Bus.objects.filter(estado="activo")
        self.fields["horario"].queryset = Horario.objects.select_related("ruta")
        self.fields["conductor"].queryset = conductores_disponibles()
        self.fields["conductor"].empty_label = "Sin conductor asignado"
