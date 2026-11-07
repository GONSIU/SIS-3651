from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from apps.core.models import TimeStampedModel
from apps.core.validators import normalizar_espacios, validar_solo_letras

# El orden coincide con date.weekday(): 0 = lunes.
DIAS_VALIDOS = ["L", "M", "X", "J", "V", "S", "D"]


def validar_dias_semana(valor: str) -> None:
    """Exige letras de DIAS_VALIDOS separadas por coma y sin repetir."""
    dias = valor.split(",")
    if any(dia not in DIAS_VALIDOS for dia in dias):
        raise ValidationError("Usa letras separadas por coma: L,M,X,J,V,S,D.", code="dias_invalidos")
    if len(set(dias)) != len(dias):
        raise ValidationError("Hay dias repetidos.", code="dias_repetidos")


class Terminal(TimeStampedModel):
    nombre = models.CharField(max_length=50, validators=[validar_solo_letras])
    ciudad = models.CharField(max_length=50, validators=[validar_solo_letras])
    direccion = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["ciudad", "nombre"]
        constraints = [
            models.UniqueConstraint(
                Lower("nombre"),
                Lower("ciudad"),
                name="uniq_terminal_nombre_ciudad",
                violation_error_message="Ya existe un terminal con ese nombre en esa ciudad.",
            )
        ]

    def __str__(self):
        return f"{self.nombre} ({self.ciudad})"

    def clean_fields(self, exclude=None):
        self.nombre = normalizar_espacios(self.nombre)
        self.ciudad = normalizar_espacios(self.ciudad)
        super().clean_fields(exclude=exclude)


class Ruta(TimeStampedModel):
    origen = models.ForeignKey(
        Terminal, related_name="rutas_origen", on_delete=models.PROTECT
    )
    destino = models.ForeignKey(
        Terminal, related_name="rutas_destino", on_delete=models.PROTECT
    )
    distancia_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    duracion_minutos = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["origen__ciudad", "destino__ciudad"]
        constraints = [
            models.CheckConstraint(
                check=Q(distancia_km__isnull=True) | Q(distancia_km__gt=0),
                name="ruta_distancia_km_positiva",
                violation_error_message="La distancia debe ser mayor a 0.",
            ),
            models.CheckConstraint(
                check=Q(duracion_minutos__isnull=True) | Q(duracion_minutos__gte=1),
                name="ruta_duracion_minutos_positiva",
                violation_error_message="La duracion debe ser de al menos 1 minuto.",
            ),
            models.CheckConstraint(
                check=~Q(origen=F("destino")),
                name="ruta_origen_distinto_destino",
                violation_error_message="El destino debe ser distinto del origen.",
            ),
            models.UniqueConstraint(
                fields=["origen", "destino"],
                name="uniq_ruta_origen_destino",
                violation_error_message="Ya existe una ruta con ese origen y destino.",
            ),
        ]

    def __str__(self):
        return f"{self.origen} → {self.destino}"


class Horario(TimeStampedModel):
    ruta = models.ForeignKey(Ruta, related_name="horarios", on_delete=models.CASCADE)
    hora_salida = models.TimeField()
    dias_semana = models.CharField(
        max_length=13, validators=[validar_dias_semana], help_text="Ej. L,M,X,J,V,S,D"
    )

    class Meta:
        ordering = ["ruta", "hora_salida"]
        constraints = [
            models.UniqueConstraint(
                fields=["ruta", "hora_salida"], name="uniq_horario_ruta_hora"
            )
        ]

    def __str__(self):
        return f"{self.ruta} — {self.hora_salida}"

    def opera_el(self, fecha) -> bool:
        """Indica si este horario sale el dia de la semana de esa fecha."""
        return DIAS_VALIDOS[fecha.weekday()] in self.dias_semana.split(",")
