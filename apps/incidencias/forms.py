from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.flota.models import Bus
from apps.personal.models import Empleado
from apps.ventas.models import Pasaje
from apps.viajes.models import Viaje
from .models import Incidencia

INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-4 py-2.5 font-body-sm text-body-sm"
SELECT_CLASSES = INPUT_CLASSES + " bg-white"
TEXTAREA_CLASSES = INPUT_CLASSES + " resize-none"
FORMATO_FECHA_HORA = "%Y-%m-%dT%H:%M"
# Viajes que se ofrecen al registrar una incidencia: los de este rango alrededor de hoy.
DIAS_VIAJES_ATRAS = 30
DIAS_VIAJES_ADELANTE = 7


class IncidenciaForm(forms.ModelForm):
    """Registro de un incidente por el personal (supervisor o admin)."""

    class Meta:
        model = Incidencia
        fields = ["categoria", "titulo", "ocurrido_en", "viaje", "bus", "empleado_involucrado", "descripcion"]
        labels = {
            "titulo": "Titulo de la incidencia",
            "ocurrido_en": "Fecha y hora del suceso",
            "viaje": "Viaje (opcional)",
            "bus": "Bus (opcional, se toma del viaje si lo eliges)",
            "empleado_involucrado": "Personal involucrado (opcional)",
            "descripcion": "Descripcion detallada",
        }
        widgets = {
            "categoria": forms.Select(attrs={"class": SELECT_CLASSES}),
            "titulo": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. Falla de frenos en ruta"}),
            "ocurrido_en": forms.DateTimeInput(
                attrs={"class": INPUT_CLASSES, "type": "datetime-local"}, format=FORMATO_FECHA_HORA
            ),
            "viaje": forms.Select(attrs={"class": SELECT_CLASSES}),
            "bus": forms.Select(attrs={"class": SELECT_CLASSES}),
            "empleado_involucrado": forms.Select(attrs={"class": SELECT_CLASSES}),
            "descripcion": forms.Textarea(
                attrs={"class": TEXTAREA_CLASSES, "rows": 6, "placeholder": "Describe lo sucedido en orden cronologico."}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoy = timezone.localdate()
        self.fields["ocurrido_en"].input_formats = [FORMATO_FECHA_HORA]
        self.fields["categoria"].choices = [("", "Selecciona una categoria")] + [
            opcion for opcion in Incidencia.CATEGORIA_CHOICES
        ]
        self.fields["viaje"].queryset = (
            Viaje.objects.filter(
                fecha_salida__range=(hoy - timedelta(days=DIAS_VIAJES_ATRAS), hoy + timedelta(days=DIAS_VIAJES_ADELANTE))
            )
            .select_related("ruta__origen", "ruta__destino", "bus")
            .order_by("-fecha_salida")
        )
        self.fields["bus"].queryset = Bus.objects.order_by("placa")
        self.fields["empleado_involucrado"].queryset = Empleado.objects.select_related("usuario").order_by(
            "usuario__first_name", "usuario__last_name"
        )
        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault("ocurrido_en", timezone.localtime().replace(second=0, microsecond=0))


class ReclamoForm(forms.ModelForm):
    """Reclamo o comentario que envia el cliente desde su cuenta."""

    calificacion = forms.TypedChoiceField(
        label="Como calificas el servicio? (opcional)",
        choices=[("", "Sin calificar")] + [(n, f"{n} de 5") for n in range(5, 0, -1)],
        coerce=int,
        empty_value=None,
        required=False,
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
    )

    class Meta:
        model = Incidencia
        fields = ["categoria", "pasaje", "titulo", "descripcion", "calificacion"]
        labels = {
            "categoria": "Tipo",
            "pasaje": "Pasaje relacionado (opcional)",
            "titulo": "Asunto",
            "descripcion": "Detalle",
        }
        widgets = {
            "categoria": forms.Select(attrs={"class": SELECT_CLASSES}),
            "pasaje": forms.Select(attrs={"class": SELECT_CLASSES}),
            "titulo": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. El bus salio con retraso"}),
            "descripcion": forms.Textarea(
                attrs={"class": TEXTAREA_CLASSES, "rows": 6, "placeholder": "Cuentanos que paso."}
            ),
        }

    def __init__(self, *args, cliente, **kwargs):
        super().__init__(*args, **kwargs)
        etiquetas = dict(Incidencia.CATEGORIA_CHOICES)
        self.fields["categoria"].choices = [(c, etiquetas[c]) for c in Incidencia.CATEGORIAS_CLIENTE]
        # Solo los pasajes de la propia cuenta: un cliente no puede reclamar sobre el pasaje de otro.
        self.fields["pasaje"].queryset = (
            Pasaje.objects.filter(cliente=cliente)
            .select_related("viaje__ruta__origen", "viaje__ruta__destino")
            .order_by("-viaje__fecha_salida")
        )
        self.fields["pasaje"].label_from_instance = lambda p: (
            f"{p.codigo_pasaje} - {p.viaje.ruta.origen.ciudad} a {p.viaje.ruta.destino.ciudad}, "
            f"{p.viaje.fecha_salida:%d/%m/%Y}"
        )
