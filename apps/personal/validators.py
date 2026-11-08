from datetime import date

from django.core.exceptions import ValidationError
from django.utils import timezone


def validar_fecha_no_futura(valor: date) -> None:
    if valor and valor > timezone.localdate():
        raise ValidationError("La fecha no puede ser futura.", code="fecha_futura")
