from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.flota.models import Bus
from apps.rutas.models import DIAS_VALIDOS, Horario, Ruta, Terminal
from apps.viajes.models import Viaje


class VentasTestCase(TestCase):
  
    @classmethod
    def setUpTestData(cls):
        origen = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        destino = Terminal.objects.create(nombre="Central", ciudad="Oruro")
        cls.ruta = Ruta.objects.create(origen=origen, destino=destino)
        cls.horario = Horario.objects.create(
            ruta=cls.ruta, hora_salida=time(8), dias_semana=",".join(DIAS_VALIDOS)
        )
        cls.bus = Bus.objects.create(
            placa="1234ABC", nombre_tipo="Semicama", capacidad_pasajeros=4, capacidad_carga_kg=0
        )
        cls.bus.crear_asientos()
        cls.hoy = timezone.localdate()
        cls.viaje = cls.crear_viaje()
        cls.asiento = cls.viaje.asientos_viaje.first()

    @classmethod
    def crear_viaje(cls, **kwargs) -> Viaje:
        datos = {
            "ruta": cls.ruta,
            "horario": cls.horario,
            "bus": cls.bus,
            "fecha_salida": cls.hoy + timedelta(days=1),
        }
        viaje = Viaje.objects.create(**{**datos, **kwargs})
        viaje.crear_asientos_desde_bus()
        return viaje
