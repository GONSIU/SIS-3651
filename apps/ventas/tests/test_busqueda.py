from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.rutas.models import Ruta
from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje
from apps.ventas.services import buscar_pasajero_por_ci, cliente_por_ci
from .base import VentasTestCase

URL = reverse("ventas:nueva_venta")


class BuscarPasajeroPorCiTests(VentasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.cliente = Usuario.objects.create_user(
            "ana", rol="cliente", ci="1234567-1B", first_name="Ana", last_name="Perez", telefono="71234567"
        )

    def vender_pasaje(self, nombre: str, ci: str, asiento_indice: int = 0) -> Pasaje:
        asiento = self.viaje.asientos_viaje.all()[asiento_indice]
        return Pasaje.objects.create(
            viaje=self.viaje, asiento_viaje=asiento, cliente_nombre=nombre, cliente_ci=ci,
            canal="ventanilla", precio=Decimal("50"),
        )

    def test_encuentra_la_cuenta_y_normaliza_el_ci(self):
        encontrado = buscar_pasajero_por_ci(" 1234567-1b ")
        self.assertEqual(
            (encontrado.nombre, encontrado.ci, encontrado.telefono, encontrado.tiene_cuenta),
            ("Ana Perez", "1234567-1B", "71234567", True),
        )

    def test_sin_cuenta_usa_la_ultima_venta(self):
        self.vender_pasaje("Luis Mamani", "7654321", 0)
        ultimo = self.vender_pasaje("Luis Alberto Mamani", "7654321", 1)
        Pasaje.objects.filter(pk=ultimo.pk).update(cliente_telefono="69876543")
        encontrado = buscar_pasajero_por_ci("7654321")
        self.assertEqual(
            (encontrado.nombre, encontrado.telefono, encontrado.tiene_cuenta),
            ("Luis Alberto Mamani", "69876543", False),
        )

    def test_cuenta_inactiva_no_cuenta(self):
        Usuario.objects.filter(pk=self.cliente.pk).update(is_active=False)
        self.assertIsNone(cliente_por_ci("1234567-1B"))
        self.assertIsNone(buscar_pasajero_por_ci("1234567-1B"))

    def test_ci_sin_registros(self):
        self.assertIsNone(buscar_pasajero_por_ci("9999999"))

    def test_ci_invalido(self):
        for ci in ("", "12", "abcdefg"):
            with self.subTest(ci=ci), self.assertRaises(ValidationError):
                buscar_pasajero_por_ci(ci)

    def test_cliente_por_ci_vacio(self):
        for ci in ("", None):
            with self.subTest(ci=ci):
                self.assertIsNone(cliente_por_ci(ci))


class NuevaVentaBusquedaViewTests(VentasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pasado_manana = cls.crear_viaje(fecha_salida=cls.hoy + timedelta(days=2))
        cls.manana = cls.hoy + timedelta(days=1)
        cls.cliente = Usuario.objects.create_user("ana", rol="cliente", ci="1234567", first_name="Ana", last_name="Perez")

    def setUp(self):
        self.client.force_login(self.vendedor)

    def vender(self, **kwargs):
        datos = {
            "viaje_id": self.viaje.pk, "asiento_viaje_id": self.asiento.pk,
            "cliente_nombre": "Ana Perez", "precio": "50.00", "metodo_pago": "efectivo",
        }
        return self.client.post(URL, {**datos, **kwargs})

    # Filtro por fecha

    def test_filtra_los_viajes_por_fecha(self):
        respuesta = self.client.get(URL, {"fecha": self.manana.isoformat()})
        self.assertEqual(list(respuesta.context["viajes"]), [self.viaje])
        self.assertEqual(respuesta.context["fecha"], self.manana)
        self.assertContains(respuesta, f"&fecha={self.manana.isoformat()}")

    def test_sin_fecha_muestra_todos(self):
        respuesta = self.client.get(URL)
        self.assertEqual(set(respuesta.context["viajes"]), {self.viaje, self.pasado_manana})

    def test_fecha_invalida_se_ignora_y_se_avisa(self):
        respuesta = self.client.get(URL, {"fecha": "2026-13-45"})
        self.assertTrue(respuesta.context["fecha_invalida"])
        self.assertEqual(len(respuesta.context["viajes"]), 2)

    def test_fecha_sin_viajes(self):
        respuesta = self.client.get(URL, {"fecha": (self.hoy + timedelta(days=30)).isoformat()})
        self.assertEqual(list(respuesta.context["viajes"]), [])
        self.assertIsNone(respuesta.context["viaje_seleccionado"])

    def test_error_de_venta_conserva_el_filtro(self):
        respuesta = self.vender(fecha=self.manana.isoformat(), precio="0")
        self.assertEqual(respuesta.context["fecha"], self.manana)

    # Asientos libres

    def test_asientos_libres_cuenta_solo_los_disponibles(self):
        self.viaje.asientos_viaje.filter(pk=self.asiento.pk).update(estado="vendido")
        fila = next(v for v in self.client.get(URL).context["viajes"] if v.pk == self.viaje.pk)
        self.assertEqual((fila.num_libres, fila.num_asientos), (3, 4))

    def test_consultas_no_dependen_de_cuantos_viajes_hay(self):
        def contar() -> int:
            with CaptureQueriesContext(connection) as consultas:
                self.client.get(URL)
            return len(consultas)

        con_dos = contar()
        for dias in (3, 4, 5):
            self.crear_viaje(fecha_salida=self.hoy + timedelta(days=dias))
        self.assertEqual(contar(), con_dos)

    # Busqueda por CI

    def test_busqueda_precarga_los_datos(self):
        respuesta = self.client.get(URL, {"viaje": self.viaje.pk, "ci_buscar": "1234567"})
        iniciales = respuesta.context["form"].initial
        self.assertEqual((iniciales["cliente_nombre"], iniciales["cliente_ci"]), ("Ana Perez", "1234567"))
        self.assertEqual(respuesta.context["viaje_seleccionado"], self.viaje)
        self.assertContains(respuesta, "Cliente con cuenta")

    def test_busqueda_sin_resultados_deja_el_ci(self):
        respuesta = self.client.get(URL, {"ci_buscar": "9999999"})
        self.assertEqual(respuesta.context["form"].initial["cliente_ci"], "9999999")
        self.assertContains(respuesta, "No hay registros con ese CI")

    def test_busqueda_con_ci_invalido_muestra_error(self):
        respuesta = self.client.get(URL, {"ci_buscar": "12"})
        self.assertTrue(respuesta.context["busqueda"]["error"])
        self.assertNotIn("cliente_ci", respuesta.context["form"].initial)

    # Precio base

    def test_precio_base_de_la_ruta_se_precarga(self):
        Ruta.objects.filter(pk=self.ruta.pk).update(precio_base=Decimal("75.50"))
        respuesta = self.client.get(URL, {"viaje": self.viaje.pk})
        self.assertEqual(respuesta.context["form"].initial["precio"], Decimal("75.50"))

    def test_sin_precio_base_el_campo_queda_vacio(self):
        respuesta = self.client.get(URL, {"viaje": self.viaje.pk})
        self.assertNotIn("precio", respuesta.context["form"].initial)

    # Enlace con la cuenta del cliente

    def test_venta_con_ci_de_una_cuenta_la_enlaza(self):
        self.vender(cliente_ci="1234567")
        self.assertEqual(Pasaje.objects.get().cliente, self.cliente)

    def test_venta_con_ci_sin_cuenta_no_enlaza(self):
        self.vender(cliente_ci="7654321")
        self.assertIsNone(Pasaje.objects.get().cliente)

    # Telefono

    def test_venta_guarda_el_telefono_normalizado(self):
        self.vender(telefono="7123-4567")
        self.assertEqual(Pasaje.objects.get().cliente_telefono, "71234567")

    def test_telefono_es_opcional(self):
        self.vender()
        self.assertEqual(Pasaje.objects.get().cliente_telefono, "")

    def test_telefono_invalido_no_vende(self):
        respuesta = self.vender(telefono="12")
        self.assertIn("telefono", respuesta.context["form"].errors)
        self.assertFalse(Pasaje.objects.exists())

    def test_telefono_invalido_se_rechaza_en_el_modelo(self):
        pasaje = Pasaje(
            viaje=self.viaje, asiento_viaje=self.asiento, cliente_nombre="Ana",
            cliente_telefono="abc", canal="ventanilla", precio=Decimal("50"),
        )
        with self.assertRaises(ValidationError) as ctx:
            pasaje.full_clean()
        self.assertIn("cliente_telefono", ctx.exception.message_dict)

    def test_cuenta_inactiva_no_se_enlaza(self):
        Usuario.objects.filter(pk=self.cliente.pk).update(is_active=False)
        self.vender(cliente_ci="1234567")
        self.assertIsNone(Pasaje.objects.get().cliente)
