from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.personal.models import Empleado
from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje
from apps.ventas.tests.base import VentasTestCase


class EmpleadoTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(username="karen", first_name="Karen", rol="ventanillero")

    def test_rechaza_fecha_de_ingreso_futura(self):
        empleado = Empleado(
            usuario=self.usuario, cargo="ventanillero", fecha_ingreso=timezone.localdate() + timedelta(days=1)
        )
        with self.assertRaises(ValidationError) as contexto:
            empleado.full_clean()
        self.assertIn("fecha_ingreso", contexto.exception.message_dict)

    def errores(self, **datos) -> dict:
        empleado = Empleado(**{"usuario": self.usuario, "fecha_ingreso": timezone.localdate(), **datos})
        try:
            empleado.full_clean()
        except ValidationError as error:
            return error.message_dict
        return {}

    def test_cargo_compatible_con_el_rol(self):
        for cargo in ("ventanillero", "encargado_encomiendas"):
            with self.subTest(cargo=cargo):
                self.assertEqual(self.errores(cargo=cargo), {})

    def test_rechaza_cargo_de_otro_rol(self):
        errores = self.errores(cargo="conductor")
        self.assertIn("Ventanillero, Encargado de encomiendas", errores["cargo"][0])

    def test_rechaza_cargo_fuera_de_la_lista(self):
        self.assertIn("cargo", self.errores(cargo="Cajera"))

    def test_constraint_rechaza_cargo_fuera_de_la_lista(self):
        # objects.create no llama a full_clean(): lo frena la CheckConstraint.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Empleado.objects.create(usuario=self.usuario, cargo="Cajera", fecha_ingreso=timezone.localdate())

    def test_cada_rol_de_personal_tiene_cargos(self):
        roles = {clave for clave, _ in Usuario.ROL_CHOICES} - {"cliente"}
        self.assertEqual(set(Empleado.CARGOS_POR_ROL), roles)
        claves = {clave for clave, _ in Empleado.CARGO_CHOICES}
        for cargos in Empleado.CARGOS_POR_ROL.values():
            self.assertTrue(set(cargos) <= claves)

    def test_str_muestra_el_nombre_del_cargo(self):
        empleado = Empleado(usuario=self.usuario, cargo="encargado_encomiendas")
        self.assertEqual(str(empleado), "Karen — Encargado de encomiendas")


class DesempenoVentanillaViewTests(VentasTestCase):
    def setUp(self):
        # La vista exige rol supervisor o admin (RolRequeridoMixin).
        self.client.force_login(Usuario.objects.create_user(
            username="sup", rol="supervisor", terminal_asignado=self.ruta.origen
        ))
        self.con_ficha = Usuario.objects.create_user(username="karen", first_name="Karen", last_name="Vargas")
        Empleado.objects.create(usuario=self.con_ficha, cargo="ventanillero", fecha_ingreso=self.hoy)
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
            [("karen", "Ventanillero", 2, Decimal("120")), ("marco", None, 1, Decimal("40"))],
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
