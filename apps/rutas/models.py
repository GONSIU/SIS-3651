from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone
from apps.core.models import TimeStampedModel
from apps.core.validators import normalizar_espacios, validar_solo_letras

# El orden coincide con date.weekday(): 0 = lunes.
DIAS_VALIDOS = ["L", "M", "X", "J", "V", "S", "D"]
CARRIL_MAXIMO = 99
NOMBRES_DIAS = {
    "L": "lunes", "M": "martes", "X": "miercoles", "J": "jueves",
    "V": "viernes", "S": "sabado", "D": "domingo",
}


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
    # Precio sugerido del pasaje. Opcional para no romper las rutas existentes; la venta
    # online lo necesitara porque el cliente no escribe el precio.
    precio_base = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    # Inactiva: no se programan viajes nuevos. Los ya programados siguen igual.
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
                check=Q(precio_base__isnull=True) | Q(precio_base__gt=0),
                name="ruta_precio_base_positivo",
                violation_error_message="El precio base debe ser mayor a 0.",
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

    def tiene_viajes(self) -> bool:
        """Con viajes la ruta no se borra (Viaje.ruta es PROTECT) ni cambia de terminales."""
        return self.pk is not None and self.viajes.exists()


class Horario(TimeStampedModel):
    ruta = models.ForeignKey(Ruta, related_name="horarios", on_delete=models.CASCADE)
    hora_salida = models.TimeField()
    dias_semana = models.CharField(
        max_length=13, validators=[validar_dias_semana], help_text="Ej. L,M,X,J,V,S,D"
    )
    # Inactivo: no se programan viajes nuevos con este horario. Es la forma de retirar un
    # horario que ya tiene viajes y por eso no se puede borrar.
    activo = models.BooleanField(default=True)
    # Carril de la terminal de origen desde donde sale este horario; se imprime en el
    # boleto. Opcional: los horarios anteriores no lo tienen. Es fijo por horario (no por
    # viaje): cambiarlo afecta a todos sus viajes, tambien a los ya vendidos.
    carril = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(CARRIL_MAXIMO)],
        help_text=f"Opcional. Numero de carril de salida (1 a {CARRIL_MAXIMO}).",
    )

    class Meta:
        ordering = ["ruta", "hora_salida"]
        constraints = [
            models.UniqueConstraint(
                fields=["ruta", "hora_salida"], name="uniq_horario_ruta_hora"
            ),
            models.CheckConstraint(
                check=Q(carril__isnull=True) | Q(carril__gte=1, carril__lte=CARRIL_MAXIMO),
                name="horario_carril_rango",
                violation_error_message=f"El carril debe estar entre 1 y {CARRIL_MAXIMO}.",
            ),
        ]

    def __str__(self):
        return f"{self.ruta} — {self.hora_salida}"

    def tiene_viajes(self) -> bool:
        """Con viajes no se borra (Viaje.horario es PROTECT) ni cambia de hora o de ruta:
        la salida programada de cada viaje se calcula con hora_salida."""
        return self.pk is not None and self.viajes.exists()

    def viajes_futuros_fuera_de(self, dias: list[str]):
        """Viajes no cancelados desde hoy que caen en un dia que no esta en `dias`."""
        hoy = timezone.localdate()
        pendientes = self.viajes.filter(fecha_salida__gte=hoy).exclude(estado="cancelado")
        return [v for v in pendientes if DIAS_VALIDOS[v.fecha_salida.weekday()] not in dias]

    def opera_el(self, fecha) -> bool:
        """Indica si este horario sale el dia de la semana de esa fecha."""
        return DIAS_VALIDOS[fecha.weekday()] in self.dias_semana.split(",")

    def dias_legibles(self) -> str:
        """Dias de salida en palabras y en orden de semana: "lunes, miercoles y viernes"."""
        dias = self.dias_semana.split(",")
        nombres = [NOMBRES_DIAS[d] for d in DIAS_VALIDOS if d in dias]
        if len(nombres) == len(DIAS_VALIDOS):
            return "todos los dias"
        if len(nombres) == 1:
            return nombres[0]
        return f"{', '.join(nombres[:-1])} y {nombres[-1]}"

    def proxima_salida(self, desde: date) -> date | None:
        """Primera fecha desde `desde` (incluida) en la que opera; None si no tiene dias."""
        for dias in range(len(DIAS_VALIDOS)):
            fecha = desde + timedelta(days=dias)
            if self.opera_el(fecha):
                return fecha
        return None
