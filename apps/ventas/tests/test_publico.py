from datetime import datetime, time, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.rutas.models import DIAS_VALIDOS, Horario, Ruta, Terminal
from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje
from apps.ventas.services import viajes_reservables_online
from apps.viajes.models import Viaje
from .base import VentasTestCase

URL_BUSCAR = reverse("ventas:buscar_viajes")


class PublicoTestCase(VentasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Ruta.objects.filter(pk=cls.ruta.pk).update(precio_base=Decimal("60.00"))
        cls.ruta.refresh_from_db()

    def url_viaje(self, viaje=None) -> str:
        return reverse("ventas:viaje_publico", args=[(viaje or self.viaje).pk])

    def url_mapa(self, viaje=None) -> str:
        return reverse("ventas:mapa_publico", args=[(viaje or self.viaje).pk])


class AccesoSinSesionTests(PublicoTestCase):
    def test_las_tres_vistas_no_piden_sesion(self):
        for url in (URL_BUSCAR, self.url_viaje(), self.url_mapa()):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_el_resto_del_sitio_sigue_exigiendo_sesion(self):
        for url in (reverse("ventas:nueva_venta"), reverse("viajes:listado")):
            with self.subTest(url=url):
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta["Location"].startswith(reverse("usuarios:login")))

    def test_el_personal_tambien_puede_consultar(self):
        self.client.force_login(self.vendedor)
        self.assertEqual(self.client.get(self.url_viaje()).status_code, 200)

    def test_no_muestra_datos_de_pasajeros(self):
        Pasaje.objects.create(
            viaje=self.viaje, asiento_viaje=self.asiento, cliente_nombre="Juana Secreta",
            cliente_ci="9876543", cliente_telefono="71112222", canal="ventanilla",
            precio=Decimal("60"), estado="pagado",
        )
        self.viaje.asientos_viaje.filter(pk=self.asiento.pk).update(estado="vendido")
        for url in (URL_BUSCAR, self.url_viaje(), self.url_mapa()):
            contenido = self.client.get(url).content.decode()
            for dato in ("Juana", "Secreta", "9876543", "71112222", "PSJ-"):
                with self.subTest(url=url, dato=dato):
                    self.assertNotIn(dato, contenido)

    def test_boton_de_login_vuelve_al_viaje(self):
        respuesta = self.client.get(self.url_viaje())
        self.assertEqual(respuesta.context["url_login"], f"{reverse('usuarios:login')}?next={self.url_viaje()}")

    def test_login_con_next_vuelve_al_viaje(self):
        cliente = Usuario.objects.create_user("cliente", rol="cliente", password="clave-segura-123")
        respuesta = self.client.post(
            f"{reverse('usuarios:login')}?next={self.url_viaje()}",
            {"username": cliente.username, "password": "clave-segura-123"},
        )
        self.assertRedirects(respuesta, self.url_viaje())


class ViajesReservablesTests(PublicoTestCase):
    def test_excluye_viajes_sin_precio_base(self):
        sin_precio = Ruta.objects.create(origen=self.ruta.destino, destino=self.ruta.origen)
        horario = Horario.objects.create(ruta=sin_precio, hora_salida=time(9), dias_semana=",".join(DIAS_VALIDOS))
        viaje = self.crear_viaje(ruta=sin_precio, horario=horario)
        self.assertNotIn(viaje, viajes_reservables_online())
        self.assertIn(self.viaje, viajes_reservables_online())

    def test_excluye_viajes_que_no_venden(self):
        for estado in Viaje.ESTADOS_SIN_VENTA:
            with self.subTest(estado=estado):
                Viaje.objects.filter(pk=self.viaje.pk).update(estado=estado)
                self.assertNotIn(self.viaje, viajes_reservables_online())
                self.assertEqual(self.client.get(self.url_viaje()).status_code, 404)
                self.assertEqual(self.client.get(self.url_mapa()).status_code, 404)

    def test_cierra_una_hora_antes_de_la_salida(self):
        salida = timezone.make_aware(datetime.combine(self.viaje.fecha_salida, self.horario.hora_salida))
        self.assertIn(self.viaje, viajes_reservables_online(ahora=salida - timedelta(minutes=61)))
        self.assertNotIn(self.viaje, viajes_reservables_online(ahora=salida - timedelta(minutes=59)))

    def test_cierre_cerca_de_medianoche(self):
        # Ahora 23:30: el limite cae al dia siguiente a las 00:30.
        horario_temprano = Horario.objects.create(ruta=self.ruta, hora_salida=time(0, 15), dias_semana=",".join(DIAS_VALIDOS))
        horario_tarde = Horario.objects.create(ruta=self.ruta, hora_salida=time(1, 0), dias_semana=",".join(DIAS_VALIDOS))
        manana = self.hoy + timedelta(days=1)
        temprano = self.crear_viaje(horario=horario_temprano, fecha_salida=manana)
        tarde = self.crear_viaje(horario=horario_tarde, fecha_salida=manana)
        ahora = timezone.make_aware(datetime.combine(self.hoy, time(23, 30)))
        reservables = set(viajes_reservables_online(ahora=ahora))
        self.assertNotIn(temprano, reservables)
        self.assertIn(tarde, reservables)


class BuscarViajesTests(PublicoTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        potosi = Terminal.objects.create(nombre="Nueva", ciudad="Potosi")
        cls.otra_ruta = Ruta.objects.create(origen=cls.ruta.origen, destino=potosi, precio_base=Decimal("80"))
        horario = Horario.objects.create(ruta=cls.otra_ruta, hora_salida=time(10), dias_semana=",".join(DIAS_VALIDOS))
        cls.viaje_potosi = cls.crear_viaje(ruta=cls.otra_ruta, horario=horario, fecha_salida=cls.hoy + timedelta(days=3))

    def buscar(self, **filtros):
        return self.client.get(URL_BUSCAR, filtros)

    def test_sin_filtros_muestra_todos_los_reservables(self):
        self.assertEqual(set(self.buscar().context["viajes"]), {self.viaje, self.viaje_potosi})

    def test_filtra_por_destino_y_fecha(self):
        self.assertEqual(list(self.buscar(destino="Potosi").context["viajes"]), [self.viaje_potosi])
        fecha = self.viaje.fecha_salida.isoformat()
        self.assertEqual(list(self.buscar(fecha=fecha).context["viajes"]), [self.viaje])

    def test_ciudades_del_select_salen_de_rutas_activas(self):
        opciones = dict(self.buscar().context["form"].fields["destino"].choices)
        self.assertEqual(set(opciones), {"", "La Paz", "Oruro", "Potosi"})
        Ruta.objects.filter(pk=self.otra_ruta.pk).update(activa=False)
        self.assertNotIn("Potosi", dict(self.buscar().context["form"].fields["destino"].choices))

    def test_fecha_pasada_muestra_error_y_ningun_viaje(self):
        respuesta = self.buscar(fecha=(self.hoy - timedelta(days=1)).isoformat())
        self.assertIn("fecha", respuesta.context["form"].errors)
        self.assertEqual(list(respuesta.context["viajes"]), [])

    def test_ciudad_inexistente_es_error_de_formulario(self):
        respuesta = self.buscar(origen="Atlantida")
        self.assertIn("origen", respuesta.context["form"].errors)


class MapaPublicoTests(PublicoTestCase):
    def test_solo_lectura_sin_radios(self):
        contenido = self.client.get(self.url_viaje()).content.decode()
        self.assertNotIn('name="asiento_viaje_id"', contenido)
        self.assertIn('id="mapa-asientos"', contenido)

    def test_el_fragmento_no_se_guarda_en_cache(self):
        respuesta = self.client.get(self.url_mapa())
        self.assertIn("no-cache", respuesta["Cache-Control"])
        self.assertNotIn("<html", respuesta.content.decode())

    def test_libera_reservas_vencidas_antes_de_mostrar(self):
        self.viaje.asientos_viaje.filter(pk=self.asiento.pk).update(estado="reservado")
        Pasaje.objects.create(
            viaje=self.viaje, asiento_viaje=self.asiento, cliente_nombre="Ana", canal="online",
            precio=Decimal("60"), estado="reservado", reservado_hasta=timezone.now() - timedelta(minutes=5),
        )
        respuesta = self.client.get(self.url_mapa())
        self.assertEqual(respuesta.context["viaje"].num_libres, 4)
        self.asiento.refresh_from_db()
        self.assertEqual(self.asiento.estado, "disponible")

    def test_la_venta_en_ventanilla_sigue_siendo_seleccionable(self):
        self.client.force_login(self.vendedor)
        contenido = self.client.get(reverse("ventas:nueva_venta"), {"viaje": self.viaje.pk}).content.decode()
        self.assertIn('name="asiento_viaje_id"', contenido)
