from datetime import date

from django import forms

from apps.rutas.models import Ruta, Terminal

from .services import MAX_DIAS_PERIODO, TIPOS_PERIODO, Periodo, periodo_predefinido

INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-3 py-2 font-body-sm text-body-sm"
SELECT_CLASSES = INPUT_CLASSES + " bg-white"


class ReporteFiltroForm(forms.Form):
    """Filtros comunes de los reportes, por querystring. Todos opcionales.

    Rango: ?periodo=diario|semanal|mensual o ?desde=YYYY-MM-DD&hasta=YYYY-MM-DD (este
    ultimo tiene prioridad). Sin nada, el mes actual. Ruta y terminal de origen filtran
    por la ruta del viaje."""

    periodo = forms.ChoiceField(choices=[(t, t) for t in TIPOS_PERIODO], required=False)
    desde = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"class": INPUT_CLASSES, "type": "date"}, format="%Y-%m-%d")
    )
    hasta = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"class": INPUT_CLASSES, "type": "date"}, format="%Y-%m-%d")
    )
    ruta = forms.ModelChoiceField(
        queryset=Ruta.objects.select_related("origen", "destino"),
        required=False,
        empty_label="Todas las rutas",
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
    )
    terminal = forms.ModelChoiceField(
        queryset=Terminal.objects.all(),
        required=False,
        empty_label="Todas las terminales",
        label="Terminal de origen",
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
    )

    def clean(self):
        datos = super().clean()
        desde, hasta = datos.get("desde"), datos.get("hasta")
        if bool(desde) != bool(hasta):
            raise forms.ValidationError("Indica las dos fechas del rango, desde y hasta.")
        if desde and hasta:
            if desde > hasta:
                raise forms.ValidationError("La fecha desde no puede ser posterior a la fecha hasta.")
            if (hasta - desde).days + 1 > MAX_DIAS_PERIODO:
                raise forms.ValidationError(f"El rango no puede superar {MAX_DIAS_PERIODO} dias.")
        return datos

    def periodo_elegido(self, hoy: date) -> Periodo:
        """Periodo de los datos validos; con datos invalidos o sin datos, el mes actual."""
        if not self.is_bound or not self.is_valid():
            return periodo_predefinido("mensual", hoy)
        datos = self.cleaned_data
        if datos.get("desde") and datos.get("hasta"):
            return Periodo(desde=datos["desde"], hasta=datos["hasta"], tipo="personalizado")
        return periodo_predefinido(datos.get("periodo") or "mensual", hoy)

    def filtros(self) -> dict:
        """Ruta y terminal elegidas (o None), solo si el formulario es valido."""
        if not self.is_bound or not self.is_valid():
            return {"ruta": None, "terminal": None}
        return {"ruta": self.cleaned_data.get("ruta"), "terminal": self.cleaned_data.get("terminal")}
