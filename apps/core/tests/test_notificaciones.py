from datetime import datetime, time, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.core.notificaciones import notificaciones_para
from apps.encomiendas.models import Encomienda
from apps.personal.models import Empleado
from apps.rutas.models import Horario
from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje
from apps.ventas.tests.base import VentasTestCase


class NotificacionesTestCase(VentasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.supervisor = Usuario.objects.create_user(
            "sup", rol="supervisor", terminal_asignado=cls.ruta.origen
        )
        cls.cliente = Usuario.objects.create_user("cli", rol="cliente")
        chofer = Usuario.objects.create_user("chofer", rol="conductor")
        cls.conductor = Empleado.objects.create(usuario=chofer, cargo="conductor", fecha_ingreso=cls.hoy)
        # Hora fija: los resultados no dependen de a que hora corre el test.
        cls.ahora = timezone.make_aware(datetime.combine(cls.hoy, time(10)))
        # Otro horario: dos viajes del mismo bus el mismo dia chocan con
        # uniq_viaje_bus_fecha_horario si comparten horario.
        cls.horario_tarde = Horario.objects.create(
            ruta=cls.ruta, hora_salida=time(18), dias_semana=cls.horario.dias_semana
        )

    def pasaje(self, viaje, indice: int = 0, **kwargs) -> Pasaje:
        asientos = list(viaje.asientos_viaje.order_by("pk"))
        datos = {
            "viaje": viaje, "asiento_viaje": asientos[indice], "cliente_nombre": "Ana Perez",
            "canal": "ventanilla", "precio": Decimal("50"), "estado": "pagado",
        }
        return Pasaje.objects.create(**{**datos, **kwargs})

    def encomienda(self, **kwargs) -> Encomienda:
        datos = {
            "viaje": self.viaje, "remitente_nombre": "Ana Perez", "remitente_ci": "1234567",
            "destinatario_nombre": "Luis Mamani", "destinatario_ci": "7654321",
            "descripcion_contenido": "Ropa", "peso_kg": Decimal("4.00"), "registrado_por": self.vendedor,
        }
        return Encomienda.objects.create(**{**datos, **kwargs})

    def cantidades(self, usuario) -> dict[str, int]:
        return {n.url: n.cantidad for n in notificaciones_para(usuario, ahora=self.ahora)}


class AlertasDeVentanillaTests(NotificacionesTestCase):
    def test_reservas_que_vencen_hoy(self):
        self.pasaje(self.viaje, 0, estado="reservado", reservado_hasta=self.ahora + timedelta(hours=3))
        self.pasaje(self.viaje, 1, estado="reservado", reservado_hasta=self.ahora + timedelta(days=1))
        self.pasaje(self.viaje, 2, estado="reservado", reservado_hasta=self.ahora - timedelta(minutes=5))
        self.assertEqual(self.cantidades(self.vendedor)[reverse("ventas:reservas_pendientes")], 1)

    def test_reprogramaciones_por_vencer(self):
        # PLAZO_REPROGRAMACION es de 7 dias y se avisa con 2 dias o menos.
        for dias_atras, indice in ((6, 0), (5, 1), (1, 2), (8, 3)):
            viaje = self.crear_viaje(fecha_salida=self.hoy - timedelta(days=dias_atras))
            self.pasaje(viaje, indice, estado="no_show")
        self.assertEqual(self.cantidades(self.vendedor)[reverse("ventas:reprogramaciones")], 2)

    def test_encomiendas_en_destino(self):
        self.encomienda(estado="en_destino")
        self.encomienda(estado="registrado")
        self.encomienda(estado="entregado")
        url = f"{reverse('encomiendas:listado')}?estado=en_destino"
        self.assertEqual(self.cantidades(self.vendedor)[url], 1)

    def test_sin_datos_no_hay_alertas(self):
        self.assertEqual(notificaciones_para(self.vendedor, ahora=self.ahora), [])

    def test_ventanillero_no_ve_alertas_de_viajes(self):
        self.crear_viaje(fecha_salida=self.hoy, estado="retrasado", minutos_retraso=20)
        self.assertNotIn(reverse("viajes:listado"), self.cantidades(self.vendedor))


class AlertasDeGestionTests(NotificacionesTestCase):
    def test_viajes_retrasados_y_sin_conductor(self):
        # self.viaje (manana, sin conductor) ya cuenta como "sin conductor".
        self.crear_viaje(fecha_salida=self.hoy, estado="retrasado", minutos_retraso=20, conductor=self.conductor)
        self.crear_viaje(fecha_salida=self.hoy, estado="cancelado", horario=self.horario_tarde)
        self.crear_viaje(fecha_salida=self.hoy + timedelta(days=2))
        alertas = {n.texto: n.cantidad for n in notificaciones_para(self.supervisor, ahora=self.ahora)}
        self.assertEqual(alertas["viaje(s) retrasados hoy"], 1)
        self.assertEqual(alertas["viaje(s) de hoy o manana sin conductor"], 1)

    def test_numero_de_consultas(self):
        # Una consulta COUNT por alerta: no crece con la cantidad de datos.
        with self.assertNumQueries(5):
            notificaciones_para(self.supervisor, ahora=self.ahora)


class AlertasPorRolTests(NotificacionesTestCase):
    def test_conductor_ve_sus_viajes_de_hoy(self):
        self.crear_viaje(fecha_salida=self.hoy, conductor=self.conductor)
        self.crear_viaje(
            fecha_salida=self.hoy, conductor=self.conductor, estado="completado", horario=self.horario_tarde
        )
        self.assertEqual(self.cantidades(self.conductor.usuario), {reverse("viajes:mis_viajes"): 1})

    def test_cliente_no_tiene_alertas(self):
        self.pasaje(self.viaje, 0, estado="reservado", reservado_hasta=self.ahora + timedelta(hours=3))
        self.assertEqual(notificaciones_para(self.cliente, ahora=self.ahora), [])


class CampanaEnElEncabezadoTests(NotificacionesTestCase):
    def test_muestra_el_total_y_los_enlaces(self):
        self.client.force_login(self.supervisor)
        respuesta = self.client.get(reverse("core:index"))
        self.assertContains(respuesta, "data-total-notificaciones")
        self.assertContains(respuesta, "sin conductor")
        self.assertContains(respuesta, f'href="{reverse("viajes:listado")}"')

    def test_sin_alertas_no_hay_contador(self):
        self.client.force_login(self.vendedor)
        respuesta = self.client.get(reverse("core:index"))
        self.assertNotContains(respuesta, "data-total-notificaciones")
        self.assertContains(respuesta, "No hay alertas pendientes")
