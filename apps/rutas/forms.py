from django import forms
from .models import DIAS_VALIDOS, Terminal, Ruta, Horario

INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2.5"
SELECT_CLASSES = INPUT_CLASSES + " bg-white"


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
        fields = ["origen", "destino", "distancia_km", "duracion_minutos", "precio_base", "activa"]
        widgets = {
            "origen": forms.Select(attrs={"class": SELECT_CLASSES}),
            "destino": forms.Select(attrs={"class": SELECT_CLASSES}),
            "distancia_km": forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 380.50", "step": "0.01"}),
            "duracion_minutos": forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 420"}),
            "precio_base": forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 120.00", "step": "0.01"}),
            "activa": forms.CheckboxInput(attrs={"class": "h-4 w-4 accent-signal-orange"}),
        }

    MENSAJE_TERMINALES_BLOQUEADOS = "No se cambia: la ruta ya tiene viajes programados."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cambiar los terminales de una ruta con viajes reescribiria el historial de
        # esos viajes y pasajes. disabled=True hace que Django ignore lo que llegue por
        # POST y use el valor guardado.
        if self.instance.tiene_viajes():
            for campo in ("origen", "destino"):
                self.fields[campo].disabled = True
                self.fields[campo].help_text = self.MENSAJE_TERMINALES_BLOQUEADOS

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
    # Mas largo que el modelo: "l, m, x" llega con espacios y clean_dias_semana los quita.
    dias_semana = forms.CharField(
        max_length=30,
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. L,M,X,J,V"}),
    )

    class Meta:
        model = Horario
        fields = ["ruta", "hora_salida", "dias_semana", "carril"]
        widgets = {
            "ruta": forms.Select(attrs={"class": SELECT_CLASSES}),
            "hora_salida": forms.TimeInput(attrs={"class": INPUT_CLASSES, "type": "time"}, format="%H:%M"),
            "carril": forms.NumberInput(attrs={"class": INPUT_CLASSES, "placeholder": "Ej. 4", "min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Al editar, un horario no cambia de ruta.
            self.fields["ruta"].disabled = True
            # Con viajes, la hora tampoco: Viaje.salida_programada se calcula con ella.
            if self.instance.tiene_viajes():
                self.fields["hora_salida"].disabled = True
                self.fields["hora_salida"].help_text = (
                    "No se cambia: hay viajes con este horario. Crea otro horario y desactiva este."
                )

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

    def clean(self):
        cleaned_data = super().clean()
        dias = cleaned_data.get("dias_semana")
        if self.instance.pk and dias:
            fuera = self.instance.viajes_futuros_fuera_de(dias.split(","))
            if fuera:
                fechas = ", ".join(f"{v.fecha_salida:%d/%m}" for v in fuera[:5])
                self.add_error(
                    "dias_semana",
                    f"Hay viajes programados en dias que quitarias ({fechas}). Cancelalos o reprogramalos antes.",
                )
        return cleaned_data
