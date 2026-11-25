from django import forms
from django.utils import timezone

from .models import Viaje
from apps.flota.models import Bus
from apps.personal.models import Empleado
from apps.rutas.models import Horario

SELECT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2.5 bg-white"
INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2.5"


def conductores_disponibles():
    """Empleados con rol conductor y cuenta activa: los unicos que pueden asignarse."""
    return (
        Empleado.objects.filter(usuario__rol="conductor", usuario__is_active=True)
        .select_related("usuario")
        .order_by("usuario__first_name", "usuario__last_name", "usuario__username")
    )


class HorarioSelect(forms.Select):
    """Select de horarios con data-dias en cada opcion: el template lo usa para
    deshabilitar los horarios que no salen el dia elegido."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        opcion = super().create_option(name, value, label, selected, index, subindex, attrs)
        horario = getattr(value, "instance", None)
        if horario is not None:
            opcion["attrs"]["data-dias"] = horario.dias_semana
        return opcion


class HorarioChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj: Horario) -> str:
        return f"{obj.ruta} - {obj.hora_salida:%H:%M} ({obj.dias_semana})"


class ViajeForm(forms.ModelForm):
    class Meta:
        model = Viaje
        # Sin "estado": todo viaje nace programado y avanza con los metodos de control
        # (marcar_retraso, registrar_salida, ...), que validan las transiciones.
        # Sin "ruta": sale de horario.ruta (ver clean). Pedirla aparte permitia elegir un
        # horario de otra ruta.
        fields = ["fecha_salida", "horario", "bus", "conductor"]
        field_classes = {"horario": HorarioChoiceField}
        help_texts = {
            "conductor": "Opcional. Solo aparecen conductores activos con ficha en Personal.",
        }
        widgets = {
            "horario": HorarioSelect(attrs={"class": SELECT_CLASSES}),
            "bus": forms.Select(attrs={"class": SELECT_CLASSES}),
            "conductor": forms.Select(attrs={"class": SELECT_CLASSES}),
            "fecha_salida": forms.DateInput(attrs={"class": INPUT_CLASSES, "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bus"].queryset = Bus.objects.filter(estado="activo")
        # La etiqueta usa ruta.origen y ruta.destino: sin este select_related seria N+1.
        self.fields["horario"].queryset = (
            Horario.objects.filter(activo=True, ruta__activa=True)
            .select_related("ruta__origen", "ruta__destino")
            .order_by("ruta__origen__ciudad", "ruta__destino__ciudad", "hora_salida")
        )
        self.fields["fecha_salida"].widget.attrs["min"] = timezone.localdate().isoformat()
        self.fields["conductor"].queryset = conductores_disponibles()
        self.fields["conductor"].empty_label = "Sin conductor asignado"

    def clean(self):
        cleaned = super().clean()
        horario = cleaned.get("horario")
        if horario is not None:
            # Viaje.clean() valida la ruta y reporta sus errores en "ruta", que no es campo
            # del formulario (Django lanzaria ValueError). Por eso se revisa aqui primero y
            # solo se asigna una ruta activa.
            if horario.ruta.activa:
                self.instance.ruta = horario.ruta
            else:
                self.add_error("horario", "La ruta de este horario esta inactiva.")
        return cleaned


class RetrasoForm(forms.Form):
    minutos = forms.IntegerField(
        min_value=1,
        max_value=Viaje.MAX_MINUTOS_RETRASO,
        label="Minutos de retraso estimado",
        widget=forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 30"}),
    )
