from datetime import time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.encomiendas.models import Encomienda
from apps.flota.models import Bus
from apps.rutas.models import DIAS_VALIDOS, Horario, Ruta, Terminal
from apps.usuarios.models import Usuario
from apps.viajes.models import Viaje


class EncomiendasTestCase(TestCase):
   
    @classmethod
    def setUpTestData(cls):
        origen = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        destino = Terminal.objects.create(nombre="Central", ciudad="Oruro")
        cls.ruta = Ruta.objects.create(origen=origen, destino=destino)
        cls.horario = Horario.objects.create(
            ruta=cls.ruta, hora_salida=time(8), dias_semana=",".join(DIAS_VALIDOS)
        )
        cls.bus = Bus.objects.create(
            placa="1234ABC", nombre_tipo="Semicama", capacidad_pasajeros=4, capacidad_carga_kg=Decimal("100")
        )
        cls.hoy = timezone.localdate()
        cls.viaje = cls.crear_viaje()
        cls.usuario = Usuario.objects.create_user(username="operador", password="clave-segura-123")

    @classmethod
    def crear_viaje(cls, **kwargs) -> Viaje:
        datos = {
            "ruta": cls.ruta,
            "horario": cls.horario,
            "bus": cls.bus,
            "fecha_salida": cls.hoy + timedelta(days=1),
        }
        return Viaje.objects.create(**{**datos, **kwargs})

    def datos_encomienda(self, **kwargs) -> dict:
        datos = {
            "viaje": self.viaje,
            "remitente_nombre": "Ana Perez",
            "remitente_ci": "1234567",
            "destinatario_nombre": "Luis Mamani",
            "destinatario_ci": "7654321",
            "descripcion_contenido": "Ropa",
            "peso_kg": Decimal("4.00"),
            "registrado_por": self.usuario,
        }
        return {**datos, **kwargs}

    def crear_encomienda(self, **kwargs) -> Encomienda:
        return Encomienda.objects.create(**self.datos_encomienda(**kwargs))
