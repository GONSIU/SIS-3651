from decimal import Decimal

from django.urls import reverse

from apps.core.busqueda import buscar
from apps.encomiendas.models import Encomienda
from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje
from apps.ventas.tests.base import VentasTestCase

URL = reverse("core:buscar")


class BusquedaTestCase(VentasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        asientos = list(cls.viaje.asientos_viaje.order_by("pk"))
        cls.cuenta = Usuario.objects.create_user("cli", rol="cliente", ci="9876543", first_name="Rosa", last_name="Quispe")
        comunes = {"viaje": cls.viaje, "canal": "ventanilla", "precio": Decimal("50"), "estado": "pagado"}
        cls.en_ventanilla = Pasaje.objects.create(
            asiento_viaje=asientos[0], cliente_nombre="Ana Perez", cliente_ci="1234567", **comunes
        )
        cls.con_cuenta = Pasaje.objects.create(asiento_viaje=asientos[1], cliente=cls.cuenta, **comunes)
        cls.con_complemento = Pasaje.objects.create(
            asiento_viaje=asientos[2], cliente_nombre="Juan Rojas", cliente_ci="5555555-1A", **comunes
        )
        cls.encomienda = Encomienda.objects.create(
            viaje=cls.viaje, remitente_nombre="Carla Perez", remitente_ci="1234567",
            destinatario_nombre="Luis Mamani", destinatario_ci="7654321",
            descripcion_contenido="Ropa", peso_kg=Decimal("4.00"), registrado_por=cls.vendedor,
        )


class BuscarTests(BusquedaTestCase):
    def test_por_ci_exacto_en_pasajes_y_encomiendas(self):
        resultados = buscar(" 1234567 ")
        self.assertEqual(resultados.criterio, "ci")
        self.assertEqual(resultados.pasajes, [self.en_ventanilla])
        self.assertEqual(resultados.encomiendas, [self.encomienda])
        self.assertEqual(buscar("7654321").encomiendas, [self.encomienda])
        self.assertEqual(buscar("123456").total, 0)  # exacto, no parcial

    def test_ci_de_la_cuenta_y_con_complemento(self):
        self.assertEqual(buscar("9876543").pasajes, [self.con_cuenta])
        self.assertEqual(buscar("5555555-1a").pasajes, [self.con_complemento])

    def test_por_nombre(self):
        resultados = buscar("perez")
        self.assertEqual(resultados.criterio, "nombre")
        self.assertEqual(resultados.pasajes, [self.en_ventanilla])
        self.assertEqual(resultados.encomiendas, [self.encomienda])
        self.assertEqual(buscar("quispe").pasajes, [self.con_cuenta])

    def test_por_codigo_separa_pasajes_de_encomiendas(self):
        resultados = buscar(self.en_ventanilla.codigo_pasaje.lower())
        self.assertEqual(resultados.criterio, "codigo")
        self.assertEqual(resultados.unico, self.en_ventanilla)
        self.assertEqual(buscar("psj-").total, 3)
        self.assertEqual(buscar("enc-").encomiendas, [self.encomienda])
        self.assertEqual(buscar("enc-").pasajes, [])

    def test_texto_corto_no_busca(self):
        resultados = buscar("ab")
        self.assertEqual((resultados.criterio, resultados.total), ("", 0))

    def test_numero_de_consultas(self):
        with self.assertNumQueries(2):
            resultados = buscar("perez")
            for pasaje in resultados.pasajes:
                str(pasaje.viaje.ruta.origen), pasaje.nombre_pasajero, pasaje.viaje.horario.hora_salida


class BuscarViewTests(BusquedaTestCase):
    def setUp(self):
        self.client.force_login(self.vendedor)

    def test_codigo_unico_va_directo(self):
        respuesta = self.client.get(URL, {"q": self.con_cuenta.codigo_pasaje})
        self.assertRedirects(respuesta, reverse("ventas:boleto", args=[self.con_cuenta.pk]))
        respuesta = self.client.get(URL, {"q": self.encomienda.codigo_guia})
        self.assertRedirects(respuesta, reverse("encomiendas:guia", args=[self.encomienda.pk]))

    def test_varios_resultados_muestran_la_lista(self):
        respuesta = self.client.get(URL, {"q": "1234567"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.en_ventanilla.codigo_pasaje)
        self.assertContains(respuesta, self.encomienda.codigo_guia)
        self.assertContains(respuesta, reverse("ventas:boleto", args=[self.en_ventanilla.pk]))

    def test_sin_texto_pide_mas_caracteres(self):
        self.assertContains(self.client.get(URL), "Escribe al menos 3 caracteres")

    def test_permisos_por_rol(self):
        conductor = Usuario.objects.create_user("chofer", rol="conductor")
        for usuario, codigo in ((self.cuenta, 403), (conductor, 403), (self.vendedor, 200)):
            with self.subTest(rol=usuario.rol):
                self.client.force_login(usuario)
                self.assertEqual(self.client.get(URL, {"q": "perez"}).status_code, codigo)
        self.client.logout()
        respuesta = self.client.get(URL)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("usuarios:login"), respuesta["Location"])

    def test_barra_solo_para_quien_puede_buscar(self):
        formulario = f'action="{URL}"'
        self.assertContains(self.client.get(reverse("core:index")), formulario)
        conductor = Usuario.objects.create_user("chofer", rol="conductor")
        self.client.force_login(conductor)
        self.assertNotContains(self.client.get(reverse("viajes:mis_viajes")), formulario)
