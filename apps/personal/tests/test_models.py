from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.personal.models import Empleado
from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje
from apps.ventas.tests.base import VentasTestCase


class EmpleadoTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(username="karen", first_name="Karen")

    def test_rechaza_fecha_de_ingreso_futura(self):
        empleado = Empleado(
            usuario=self.usuario, cargo="Cajera", fecha_ingreso=timezone.localdate() + timedelta(days=1)
        )
        with self.assertRaises(ValidationError) as contexto:
            empleado.full_clean()
        self.assertIn("fecha_ingreso", contexto.exception.message_dict)

    def test_normaliza_cargo(self):
        empleado = Empleado(usuario=self.usuario, cargo="  Jefe   de terminal ", fecha_ingreso=timezone.localdate())
        empleado.full_clean()
        self.assertEqual(empleado.cargo, "Jefe de terminal")


class DesempenoVentanillaViewTests(VentasTestCase):
    def setUp(self):
        # La vista exige rol supervisor o admin (RolRequeridoMixin).
        self.client.force_login(Usuario.objects.create_user(
            username="sup", rol="supervisor", terminal_asignado=self.ruta.origen
        ))
        self.con_ficha = Usuario.objects.create_user(username="karen", first_name="Karen", last_name="Vargas")
        Empleado.objects.create(usuario=self.con_ficha, cargo="Ventanillera", fecha_ingreso=self.hoy)
        self.sin_ficha = Usuario.objects.create_user(username="marco")
        asientos = list(self.viaje.asientos_viaje.all())
        for asiento, vendedor, precio in (
            (asientos[0], self.con_ficha, "50"),
            (asientos[1], self.con_ficha, "70"),
            (asientos[2], self.sin_ficha, "40"),
        ):
            Pasaje.objects.create(
                viaje=self.viaje, asiento_viaje=asiento, cliente_nombre="Ana Perez",
                canal="ventanilla", precio=Decimal(precio), vendido_por=vendedor,
            )

    def test_agrupa_por_vendedor(self):
        respuesta = self.client.get(reverse("personal:desempeno"))
        filas = respuesta.context["filas"]
        self.assertEqual(
            [(f["username"], f["cargo"], f["ventas_realizadas"], f["monto_total_vendido"]) for f in filas],
            [("karen", "Ventanillera", 2, Decimal("120")), ("marco", None, 1, Decimal("40"))],
        )
        self.assertEqual(respuesta.context["total_monto"], Decimal("160"))
        self.assertContains(respuesta, "Sin ficha de empleado")

    def test_otra_fecha_sin_ventas(self):
        ayer = self.hoy - timedelta(days=1)
        respuesta = self.client.get(reverse("personal:desempeno"), {"fecha": ayer.isoformat()})
        self.assertEqual(respuesta.context["filas"], [])

    def test_fecha_invalida_usa_hoy(self):
        respuesta = self.client.get(reverse("personal:desempeno"), {"fecha": "2026-13-40"})
        self.assertFalse(respuesta.context["fecha_valida"])
        self.assertEqual(respuesta.context["fecha"], self.hoy)
