from django import forms
from .models import Terminal, Ruta, Horario

INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2.5"
SELECT_CLASSES = INPUT_CLASSES + " bg-white"

DIAS_VALIDOS = ["L", "M", "X", "J", "V", "S", "D"]


class TerminalForm(forms.ModelForm):
    class Meta:
        model = Terminal
        fields = ["nombre", "ciudad", "direccion"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. Terminal Bimodal"}),
            "ciudad": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. Santa Cruz"}),
            "direccion": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. Av. Intermodal s/n"}),
        }


class RutaForm(forms.ModelForm):
    class Meta:
        model = Ruta
        fields = ["origen", "destino", "distancia_km", "duracion_minutos", "activa"]
        widgets = {
            "origen": forms.Select(attrs={"class": SELECT_CLASSES}),
            "destino": forms.Select(attrs={"class": SELECT_CLASSES}),
            "distancia_km": forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 380.50", "step": "0.01"}),
            "duracion_minutos": forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 420"}),
            "activa": forms.CheckboxInput(attrs={"class": "h-4 w-4 accent-signal-orange"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        origen = cleaned_data.get("origen")
        destino = cleaned_data.get("destino")
        if not origen or not destino:
            return cleaned_data

        if origen == destino:
            self.add_error("destino", "El destino debe ser distinto del origen.")
            return cleaned_data

        duplicadas = Ruta.objects.filter(origen=origen, destino=destino)
        if self.instance.pk:
            duplicadas = duplicadas.exclude(pk=self.instance.pk)
        if duplicadas.exists():
            raise forms.ValidationError(f"Ya existe una ruta de {origen} a {destino}.")
        return cleaned_data


class HorarioForm(forms.ModelForm):
    class Meta:
        model = Horario
        fields = ["ruta", "hora_salida", "dias_semana"]
        widgets = {
            "ruta": forms.Select(attrs={"class": SELECT_CLASSES}),
            "hora_salida": forms.TimeInput(attrs={"class": INPUT_CLASSES, "type": "time"}, format="%H:%M"),
            "dias_semana": forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. L,M,X,J,V"}),
        }

    def clean_dias_semana(self) -> str:
        """Normaliza 'l, m ,x' -> 'L,M,X' y rechaza dias desconocidos o repetidos."""
        valor = self.cleaned_data["dias_semana"]
        dias = [d.strip().upper() for d in valor.split(",") if d.strip()]
        invalidos = [d for d in dias if d not in DIAS_VALIDOS]
        if not dias or invalidos:
            raise forms.ValidationError("Usa letras separadas por coma: L,M,X,J,V,S,D.")
        if len(set(dias)) != len(dias):
            raise forms.ValidationError("Hay dias repetidos.")
        return ",".join(sorted(dias, key=DIAS_VALIDOS.index))
