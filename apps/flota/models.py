from django.db import models


class Bus(models.Model):
    ESTADO_CHOICES = [
        ("activo", "Activo"),
        ("mantenimiento", "Mantenimiento"),
        ("fuera_servicio", "Fuera de Servicio"),
    ]
    PISOS_CHOICES = [(1, "1 piso"), (2, "2 pisos")]

    placa = models.CharField(max_length=20, unique=True)
    nombre_tipo = models.CharField(max_length=50, help_text="Ej. Leito, Cama, Semicama")
    capacidad_pasajeros = models.PositiveIntegerField()
    capacidad_carga_kg = models.DecimalField(max_digits=8, decimal_places=2)
    pisos = models.PositiveSmallIntegerField(choices=PISOS_CHOICES, default=1)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="activo")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["placa"]

    def __str__(self):
        return f"{self.placa} ({self.nombre_tipo})"

    # Mapea la posición visual al desplazamiento de numeración real dentro de la fila.
    # Patrón 2+pasillo+2 (Normal/Semicama): 0=ventana izq, 1=pasillo izq, 2=pasillo der, 3=ventana der.
    _OFFSET_4_POR_FILA = {0: 1, 1: 2, 2: 4, 3: 3}
    # Patrón 2+pasillo+1 (Leito/Cama): asientos más anchos, un solo asiento al lado derecho.
    _OFFSET_3_POR_FILA = {0: 1, 1: 2, 2: 3}
    # Palabras clave en nombre_tipo que identifican el patrón de 3 por fila.
    _TIPOS_3_POR_FILA = ("leito", "cama")

    def _layout_asientos(self):
        """Determina cuántos asientos por fila y su numeración según nombre_tipo."""
        tipo = (self.nombre_tipo or "").lower()
        if any(palabra in tipo for palabra in self._TIPOS_3_POR_FILA):
            return 3, self._OFFSET_3_POR_FILA
        return 4, self._OFFSET_4_POR_FILA

    def crear_asientos(self):
        """Genera el mapa de asientos repartiendo la capacidad entre los pisos del
        bus, usando 2+pasillo+2 por fila (Normal/Semicama) o 2+pasillo+1 por fila
        (Leito/Cama, según nombre_tipo). No duplica asientos ya existentes."""
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
    fila = models.PositiveIntegerField(null=True, blank=True)
    columna = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1-4: ventana/pasillo por lado")
    piso = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["bus", "piso", "fila", "columna"]
        constraints = [
            models.UniqueConstraint(fields=["bus", "numero"], name="uniq_asiento_bus_numero")
        ]

    def __str__(self):
        return f"{self.bus.placa} — Asiento {self.numero}"
