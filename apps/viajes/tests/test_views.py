from datetime import time, timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.flota.models import Bus
from apps.rutas.models import DIAS_VALIDOS, Horario, Ruta, Terminal
from apps.usuarios.models import Usuario
from apps.viajes.models import Viaje


class ListaViajesViewTests(TestCase):
    url = reverse("viajes:listado")

    @classmethod
    def setUpTestData(cls):
        origen = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        destino = Terminal.objects.create(nombre="Central", ciudad="Oruro")
        cls.ruta = Ruta.objects.create(origen=origen, destino=destino)
        cls.horario = Horario.objects.create(
            ruta=cls.ruta, hora_salida=time(8), dias_semana=",".join(DIAS_VALIDOS)
        )
        cls.supervisor = Usuario.objects.create_user("super", rol="supervisor", terminal_asignado=origen)
        cls.manana = timezone.localdate() + timedelta(days=1)

    def setUp(self):
        self.client.force_login(self.supervisor)

    def crear_viaje(self, placa: str, dias: int = 0) -> Viaje:
        bus = Bus.objects.create(placa=placa, nombre_tipo="Semicama", capacidad_pasajeros=8, capacidad_carga_kg=0)
        bus.crear_asientos()
        viaje = Viaje.objects.create(
            ruta=self.ruta, horario=self.horario, bus=bus, fecha_salida=self.manana + timedelta(days=dias)
        )
        viaje.crear_asientos_desde_bus()
        return viaje

    def consultas_del_listado(self) -> int:
        with CaptureQueriesContext(connection) as consultas:
            self.assertEqual(self.client.get(self.url).status_code, 200)
        return len(consultas)

    def test_numero_de_consultas_no_depende_de_cuantos_viajes_hay(self):
        self.crear_viaje("1111AAA")
        con_uno = self.consultas_del_listado()
        self.crear_viaje("2222BBB", dias=1)
        self.crear_viaje("3333CCC", dias=2)
        self.assertEqual(self.consultas_del_listado(), con_uno)

    def test_ocupacion_cuenta_solo_asientos_vendidos(self):
        viaje = self.crear_viaje("1111AAA")
        ids = list(viaje.asientos_viaje.values_list("pk", flat=True)[:3])
        viaje.asientos_viaje.filter(pk__in=ids[:2]).update(estado="vendido")
        viaje.asientos_viaje.filter(pk=ids[2]).update(estado="reservado")
        (fila,) = self.client.get(self.url).context["viajes"]
        self.assertEqual(fila.ocupacion_texto, "2/8")

    def test_viaje_sin_asientos_muestra_guion(self):
        bus = Bus.objects.create(placa="4444DDD", nombre_tipo="Cama", capacidad_pasajeros=8, capacidad_carga_kg=0)
        Viaje.objects.create(ruta=self.ruta, horario=self.horario, bus=bus, fecha_salida=self.manana)
        (fila,) = self.client.get(self.url).context["viajes"]
        self.assertEqual(fila.ocupacion_texto, "—")
