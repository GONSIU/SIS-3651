from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from apps.core.validators import normalizar_placa, validar_placa


class Bus(models.Model):
    ESTADO_CHOICES = [
        ("activo", "Activo"),
        ("mantenimiento", "Mantenimiento"),
        ("fuera_servicio", "Fuera de Servicio"),
    ]
    PISOS_CHOICES = [(1, "1 piso"), (2, "2 pisos")]
    TIPO_CHOICES = [
        ("Leito", "Leito"),
        ("Cama", "Cama"),
        ("Semicama", "Semicama"),
    ]

    placa = models.CharField(max_length=10, unique=True, validators=[validar_placa])
    nombre_tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    capacidad_pasajeros = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(80)]
    )
    capacidad_carga_kg = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(0)]
    )
    pisos = models.PositiveSmallIntegerField(choices=PISOS_CHOICES, default=1)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="activo")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["placa"]
        constraints = [
            models.CheckConstraint(
                check=Q(capacidad_pasajeros__gte=1, capacidad_pasajeros__lte=80),
                name="bus_capacidad_pasajeros_rango",
                violation_error_message="La capacidad debe estar entre 1 y 80 pasajeros.",
            ),
            models.CheckConstraint(
                check=Q(capacidad_carga_kg__gte=0),
                name="bus_capacidad_carga_no_negativa",
                violation_error_message="La capacidad de carga no puede ser negativa.",
            ),
        ]

    def __str__(self):
        return f"{self.placa} ({self.nombre_tipo})"

    def clean_fields(self, exclude=None):
        self.placa = normalizar_placa(self.placa)
        super().clean_fields(exclude=exclude)

    _OFFSET_4_POR_FILA = {0: 1, 1: 2, 2: 4, 3: 3}
    _OFFSET_3_POR_FILA = {0: 1, 1: 2, 2: 3}
    _TIPOS_3_POR_FILA = ("leito",)

    def _layout_asientos(self):
        tipo = (self.nombre_tipo or "").lower()
        if any(palabra in tipo for palabra in self._TIPOS_3_POR_FILA):
            return 3, self._OFFSET_3_POR_FILA
        return 4, self._OFFSET_4_POR_FILA

    def crear_asientos(self):
        
        asientos_por_fila, offsets = self._layout_asientos()
        capacidad_restante = self.capacidad_pasajeros
        numero_base = 0
        nuevos = []

        for piso in range(1, self.pisos + 1):
            pisos_faltantes = self.pisos - piso + 1
            capacidad_piso = -(-capacidad_restante // pisos_faltantes)  # redondeo hacia arriba
            capacidad_restante -= capacidad_piso

            for i in range(capacidad_piso):
                fila = i // asientos_por_fila + 1
                posicion = i % asientos_por_fila
                numero = numero_base + (fila - 1) * asientos_por_fila + offsets[posicion]
                nuevos.append(
                    Asiento(bus=self, numero=str(numero), fila=fila, columna=posicion + 1, piso=piso)
                )
            numero_base += capacidad_piso

        Asiento.objects.bulk_create(nuevos, ignore_conflicts=True)


class Asiento(models.Model):
    bus = models.ForeignKey(Bus, related_name="asientos", on_delete=models.CASCADE)
    numero = models.CharField(max_length=5)
    fila = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    columna = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        help_text="1-4: ventana/pasillo por lado",
    )
    piso = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["bus", "piso", "fila", "columna"]
        constraints = [
            models.UniqueConstraint(fields=["bus", "numero"], name="uniq_asiento_bus_numero"),
            models.CheckConstraint(
                check=Q(fila__isnull=True) | Q(fila__gte=1),
                name="asiento_fila_positiva",
                violation_error_message="La fila debe ser mayor o igual a 1.",
            ),
            models.CheckConstraint(
                check=Q(columna__isnull=True) | Q(columna__gte=1, columna__lte=4),
                name="asiento_columna_rango",
                violation_error_message="La columna debe estar entre 1 y 4.",
            ),
            models.CheckConstraint(
                check=Q(piso__gte=1),
                name="asiento_piso_positivo",
                violation_error_message="El piso debe ser mayor o igual a 1.",
            ),
        ]

    def __str__(self):
        return f"{self.bus.placa} — Asiento {self.numero}"

    def clean(self):
        super().clean()
        if self.bus_id and self.piso and self.piso > self.bus.pisos:
            raise ValidationError({"piso": f"El bus solo tiene {self.bus.pisos} piso(s)."})
