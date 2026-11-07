from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.usuarios.models import Usuario
from apps.ventas.models import Pago, Pasaje
from apps.viajes.models import Viaje
from .base import VentasTestCase


class PasajeTests(VentasTestCase):
    def pasaje(self, **kwargs) -> Pasaje:
        datos = {
            "viaje": self.viaje,
            "asiento_viaje": self.asiento,
            "cliente_nombre": "Ana Perez",
            "canal": "ventanilla",
            "precio": Decimal("50"),
        }
        return Pasaje(**{**datos, **kwargs})

    def errores(self, pasaje: Pasaje) -> dict:
        with self.assertRaises(ValidationError) as error:
            pasaje.full_clean()
        return error.exception.message_dict

    def test_pasaje_valido_y_normalizado(self):
        pasaje = self.pasaje(cliente_nombre=" Ana   Perez", cliente_ci="1234567-1b")
        pasaje.full_clean()
        self.assertEqual(pasaje.cliente_nombre, "Ana Perez")
        self.assertEqual(pasaje.cliente_ci, "1234567-1B")

    def test_limites_de_precio(self):
        self.pasaje(precio=Decimal("0.01")).full_clean()
        for valor in (Decimal("0"), Decimal("-1")):
            with self.subTest(valor=valor):
                self.assertIn("precio", self.errores(self.pasaje(precio=valor)))

    def test_rechaza_datos_del_pasajero_invalidos(self):
        self.assertIn("cliente_nombre", self.errores(self.pasaje(cliente_nombre="as12")))
        self.assertIn("cliente_ci", self.errores(self.pasaje(cliente_ci="asca")))

    def test_exige_cliente_o_nombre(self):
        self.assertIn("cliente_nombre", self.errores(self.pasaje(cliente_nombre="")))
        cliente = Usuario.objects.create(username="ana")
        self.pasaje(cliente=cliente, cliente_nombre="").full_clean()

    def test_constraints_en_base_de_datos(self):
        for datos in ({"precio": Decimal("0")}, {"cliente_nombre": ""}):
            with self.subTest(datos=datos):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.pasaje(**datos).save()

    def test_asiento_debe_ser_del_viaje(self):
        otro_viaje = self.crear_viaje(fecha_salida=self.hoy + timedelta(days=2))
        pasaje = self.pasaje(asiento_viaje=otro_viaje.asientos_viaje.first())
        self.assertIn("asiento_viaje", self.errores(pasaje))

    def test_no_se_vende_en_viaje_cancelado_o_completado(self):
        for estado in ("cancelado", "completado"):
            with self.subTest(estado=estado):
                Viaje.objects.filter(pk=self.viaje.pk).update(estado=estado)
                viaje = Viaje.objects.get(pk=self.viaje.pk)
                self.assertIn("viaje", self.errores(self.pasaje(viaje=viaje)))

    def test_no_se_vende_si_la_fecha_ya_paso(self):
        Viaje.objects.filter(pk=self.viaje.pk).update(fecha_salida=self.hoy - timedelta(days=1))
        viaje = Viaje.objects.get(pk=self.viaje.pk)
        self.assertIn("viaje", self.errores(self.pasaje(viaje=viaje)))

    def test_se_vende_para_un_viaje_de_hoy(self):
        Viaje.objects.filter(pk=self.viaje.pk).update(fecha_salida=self.hoy)
        self.pasaje(viaje=Viaje.objects.get(pk=self.viaje.pk)).full_clean()

    def test_asiento_debe_estar_disponible(self):
        for estado in ("reservado", "vendido", "bloqueado"):
            with self.subTest(estado=estado):
                self.asiento.estado = estado
                self.assertIn("asiento_viaje", self.errores(self.pasaje()))

    def test_pasaje_vendido_se_puede_editar_tras_cancelar_el_viaje(self):
        pasaje = self.pasaje()
        pasaje.save()
        pasaje.marcar_como_vendido()
        Viaje.objects.filter(pk=self.viaje.pk).update(estado="cancelado")
        pasaje = Pasaje.objects.get(pk=pasaje.pk)
        pasaje.full_clean()


class PagoTests(VentasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.pasaje = Pasaje.objects.create(
            viaje=cls.viaje,
            asiento_viaje=cls.asiento,
            cliente_nombre="Ana Perez",
            canal="ventanilla",
            precio=Decimal("100"),
        )

    def pago(self, **kwargs) -> Pago:
        datos = {"pasaje": self.pasaje, "metodo": "efectivo", "monto": Decimal("100")}
        return Pago(**{**datos, **kwargs})

    def errores(self, pago: Pago) -> dict:
        with self.assertRaises(ValidationError) as error:
            pago.full_clean()
        return error.exception.message_dict

    def test_limites_de_monto(self):
        self.pago(monto=Decimal("0.01")).full_clean()
        for valor in (Decimal("0"), Decimal("-1")):
            with self.subTest(valor=valor):
                self.assertIn("monto", self.errores(self.pago(monto=valor)))

    def test_constraint_de_monto(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.pago(monto=Decimal("0")).save()

    def test_pagos_no_superan_el_precio(self):
        self.pago(monto=Decimal("60")).save()
        self.pago(monto=Decimal("40")).full_clean()
        self.assertIn("monto", self.errores(self.pago(monto=Decimal("40.01"))))

    def test_editar_un_pago_no_se_suma_a_si_mismo(self):
        pago = self.pago()
        pago.save()
        pago.full_clean()

    def test_referencia_obligatoria_salvo_en_efectivo(self):
        self.pago(metodo="efectivo").full_clean()
        for metodo in ("tarjeta", "qr", "transferencia"):
            with self.subTest(metodo=metodo):
                self.assertIn("referencia_externa", self.errores(self.pago(metodo=metodo)))
                self.pago(metodo=metodo, referencia_externa="ABC123").full_clean()
