from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.rutas.models import Ruta
from apps.core.validators import (
    normalizar_ci,
    normalizar_espacios,
    normalizar_telefono,
    validar_ci,
    validar_nombre_persona,
    validar_telefono,
)
from .models import Pago
from .validators import validar_nit_o_ci

INPUT_CLASSES = "form-input-custom w-full border border-outline-variant rounded px-4 py-2.5 font-body-sm text-body-sm"
SELECT_CLASSES = INPUT_CLASSES + " bg-white"


class FacturacionMixin(forms.Form):
    """NIT o CI y razon social opcionales, los dos o ninguno. Lo usan la venta en
    ventanilla, la reserva online y el cobro del saldo."""

    nit = forms.CharField(
        max_length=18, required=False, label="NIT o CI para la factura",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES}),
    )
    razon_social = forms.CharField(
        max_length=120, required=False, label="Razon social",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES}),
    )

    def clean_nit(self) -> str:
        valor = normalizar_ci(self.cleaned_data["nit"])
        if valor:
            validar_nit_o_ci(valor)
        return valor

    def clean_razon_social(self) -> str:
        return normalizar_espacios(self.cleaned_data["razon_social"])

    def clean(self):
        cleaned_data = super().clean()
        if bool(cleaned_data.get("nit")) != bool(cleaned_data.get("razon_social")):
            campo = "razon_social" if cleaned_data.get("nit") else "nit"
            self.add_error(campo, "Para facturar completa el NIT o CI y la razon social.")
        return cleaned_data


class VentaForm(FacturacionMixin, forms.Form):
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


def ciudades_con_rutas() -> list[tuple[str, str]]:
    """Ciudades de origen o destino de alguna ruta activa, para los select de busqueda."""
    ciudades = set()
    for origen, destino in Ruta.objects.filter(activa=True).values_list("origen__ciudad", "destino__ciudad"):
        ciudades.update((origen, destino))
    return [("", "Cualquiera")] + [(c, c) for c in sorted(ciudades)]


class BuscarViajeForm(forms.Form):
    """Busqueda publica de viajes. Todos los campos son opcionales."""

    origen = forms.ChoiceField(required=False, widget=forms.Select(attrs={"class": SELECT_CLASSES}))
    destino = forms.ChoiceField(required=False, widget=forms.Select(attrs={"class": SELECT_CLASSES}))
    fecha = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": INPUT_CLASSES, "type": "date"}, format="%Y-%m-%d"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Se calculan en cada formulario para que una ruta nueva aparezca sin reiniciar.
        opciones = ciudades_con_rutas()
        self.fields["origen"].choices = opciones
        self.fields["destino"].choices = opciones

    def clean_fecha(self):
        fecha = self.cleaned_data["fecha"]
        if fecha and fecha < timezone.localdate():
            raise forms.ValidationError("La fecha no puede ser pasada.")
        return fecha

    def filtrar(self, viajes):
        """Aplica los filtros validos al queryset de viajes."""
        datos = self.cleaned_data
        if datos.get("origen"):
            viajes = viajes.filter(ruta__origen__ciudad=datos["origen"])
        if datos.get("destino"):
            viajes = viajes.filter(ruta__destino__ciudad=datos["destino"])
        if datos.get("fecha"):
            viajes = viajes.filter(fecha_salida=datos["fecha"])
        return viajes


class ReservaForm(FacturacionMixin, forms.Form):
    """Datos para reservar online: pasajero, facturacion (opcional), pago y condiciones.

    El viaje, el asiento y el precio no vienen del formulario: la vista los toma de la URL
    y del viaje, y el servicio los vuelve a validar."""

    METODOS_ONLINE = [opcion for opcion in Pago.METODO_CHOICES if opcion[0] != "efectivo"]

    cliente_nombre = forms.CharField(
        max_length=100, label="Nombre completo del pasajero",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "autocomplete": "name"}),
    )
    cliente_ci = forms.CharField(
        max_length=12, label="CI del pasajero",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES}),
    )
    cliente_telefono = forms.CharField(
        max_length=15, label="Telefono del pasajero",
        help_text="Para avisarte si el viaje se retrasa o se cancela.",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "+591", "autocomplete": "tel"}),
    )
    monto = forms.DecimalField(
        max_digits=8, decimal_places=2, label="Monto a pagar ahora (Bs)",
        widget=forms.NumberInput(attrs={"class": INPUT_CLASSES, "step": "0.01"}),
    )
    metodo = forms.ChoiceField(
        choices=METODOS_ONLINE, label="Metodo de pago",
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
    )
    referencia = forms.CharField(
        max_length=100, label="Referencia de la transaccion",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES, "placeholder": "Codigo del QR, tarjeta o transferencia"}),
    )
    acepta_condiciones = forms.BooleanField(
        label="Acepto que el pago no es reembolsable y que, si pago un anticipo, debo pagar el saldo en ventanilla antes del plazo.",
        error_messages={"required": "Debes aceptar las condiciones para reservar."},
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4 accent-signal-orange"}),
    )

    def __init__(self, *args, precio: Decimal, monto_minimo: Decimal, **kwargs):
        super().__init__(*args, **kwargs)
        self.precio = precio
        self.monto_minimo = monto_minimo
        self.fields["monto"].min_value = monto_minimo
        self.fields["monto"].max_value = precio
        self.fields["monto"].widget.attrs.update({"min": str(monto_minimo), "max": str(precio)})
        self.fields["monto"].help_text = f"Minimo Bs {monto_minimo} (30 %), maximo Bs {precio} (total)."

    def clean_cliente_nombre(self) -> str:
        valor = normalizar_espacios(self.cleaned_data["cliente_nombre"])
        validar_nombre_persona(valor)
        return valor

    def clean_cliente_ci(self) -> str:
        valor = normalizar_ci(self.cleaned_data["cliente_ci"])
        validar_ci(valor)
        return valor

    def clean_cliente_telefono(self) -> str:
        valor = normalizar_telefono(self.cleaned_data["cliente_telefono"])
        validar_telefono(valor)
        return valor


class CobrarSaldoForm(FacturacionMixin, forms.Form):
    """Cobro del saldo de una reserva. El monto no se escribe: es el saldo del servidor."""

    metodo = forms.ChoiceField(
        choices=Pago.METODO_CHOICES, label="Metodo de pago",
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
    )
    referencia = forms.CharField(
        max_length=100, required=False, label="Referencia (QR, tarjeta o transferencia)",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES}),
    )

    def clean(self):
        cleaned_data = super().clean()
        metodo = cleaned_data.get("metodo")
        if metodo and metodo != "efectivo" and not cleaned_data.get("referencia"):
            self.add_error("referencia", "Este metodo de pago necesita una referencia.")
        return cleaned_data


class ReprogramarForm(FacturacionMixin, forms.Form):
    """Asiento del viaje nuevo, su precio y el pago del cargo (y la diferencia).

    El monto no se escribe: lo calcula el servidor con calcular_reprogramacion()."""

    asiento_viaje_id = forms.IntegerField(
        widget=forms.HiddenInput, error_messages={"required": "Elige un asiento en el mapa."}
    )
    precio = forms.DecimalField(
        max_digits=8, decimal_places=2, min_value=Decimal("0.01"), label="Precio del viaje nuevo (Bs)",
        widget=forms.NumberInput(attrs={"class": INPUT_CLASSES, "step": "0.01"}),
    )
    metodo_pago = forms.ChoiceField(
        choices=Pago.METODO_CHOICES, label="Metodo de pago",
        widget=forms.Select(attrs={"class": SELECT_CLASSES}),
    )
    referencia = forms.CharField(
        max_length=100, required=False, label="Referencia (QR, tarjeta o transferencia)",
        widget=forms.TextInput(attrs={"class": INPUT_CLASSES}),
    )

    def clean(self):
        cleaned_data = super().clean()
        metodo = cleaned_data.get("metodo_pago")
        if metodo and metodo != "efectivo" and not cleaned_data.get("referencia"):
            self.add_error("referencia", "Este metodo de pago necesita una referencia.")
        return cleaned_data
