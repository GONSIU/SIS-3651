from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.encomiendas.models import ComprobanteEncomienda, Encomienda, PagoEncomienda
from apps.viajes.models import Viaje
from .base import EncomiendasTestCase


class EncomiendaTests(EncomiendasTestCase):
    def assertErrorEn(self, encomienda: Encomienda, campo: str, texto: str):
        with self.assertRaises(ValidationError) as contexto:
            encomienda.full_clean()
        mensajes = contexto.exception.message_dict.get(campo, [])
        self.assertTrue(any(texto in m for m in mensajes), f"{campo}: {mensajes}")

    def test_genera_codigo_y_precio_al_guardar(self):
        encomienda = self.crear_encomienda(peso_kg=Decimal("4.00"), valor_declarado=Decimal("500"))
        self.assertTrue(encomienda.codigo_guia.startswith("ENC-"))
        # 10 base + 4 kg * 2.50 + 1% de 500
        self.assertEqual(encomienda.precio_envio, Decimal("25.00"))
        self.assertEqual(encomienda.estado, "registrado")

    def test_tarifa_sin_valor_declarado(self):
        desglose = Encomienda.calcular_tarifa(Decimal("1.25"), None)
        self.assertEqual(desglose["cargo_peso"], Decimal("3.13"))
        self.assertEqual(desglose["seguro"], Decimal("0.00"))
        self.assertEqual(desglose["total"], Decimal("13.13"))

    def test_precio_no_cambia_si_ya_existe(self):
        encomienda = self.crear_encomienda(precio_envio=Decimal("99.00"))
        self.assertEqual(encomienda.precio_envio, Decimal("99.00"))

    def test_normaliza_antes_de_validar(self):
        encomienda = Encomienda(
            **self.datos_encomienda(
                remitente_nombre="  Ana   Perez ",
                remitente_ci="1234567-1b",
                remitente_telefono="7123-4567",
            )
        )
        encomienda.full_clean(exclude=["precio_envio"])
        self.assertEqual(encomienda.remitente_nombre, "Ana Perez")
        self.assertEqual(encomienda.remitente_ci, "1234567-1B")
        self.assertEqual(encomienda.remitente_telefono, "71234567")

    def test_rechaza_datos_de_persona_invalidos(self):
        encomienda = Encomienda(**self.datos_encomienda(destinatario_nombre="Luis 123", destinatario_ci="12"))
        with self.assertRaises(ValidationError) as contexto:
            encomienda.full_clean(exclude=["precio_envio"])
        self.assertIn("destinatario_nombre", contexto.exception.message_dict)
        self.assertIn("destinatario_ci", contexto.exception.message_dict)

    def test_no_acepta_viaje_cancelado(self):
        Viaje.objects.filter(pk=self.viaje.pk).update(estado="cancelado")
        self.viaje.refresh_from_db()
        self.assertErrorEn(Encomienda(**self.datos_encomienda()), "viaje", "el viaje esta cancelado")

    def test_no_acepta_viaje_pasado(self):
        Viaje.objects.filter(pk=self.viaje.pk).update(fecha_salida=self.hoy - timedelta(days=1))
        self.viaje.refresh_from_db()
        self.assertErrorEn(Encomienda(**self.datos_encomienda()), "viaje", "la fecha de salida ya paso")

    def test_nueva_debe_empezar_registrada(self):
        self.assertErrorEn(Encomienda(**self.datos_encomienda(estado="entregado")), "estado", "registrada")

    def test_respeta_capacidad_de_carga(self):
        self.crear_encomienda(peso_kg=Decimal("90"))
        self.assertErrorEn(
            Encomienda(**self.datos_encomienda(peso_kg=Decimal("10.01"))), "peso_kg", "disponible: 10.00 kg"
        )
        Encomienda(**self.datos_encomienda(peso_kg=Decimal("10"))).full_clean(exclude=["precio_envio"])

    def test_extraviadas_no_ocupan_bodega(self):
        self.crear_encomienda(peso_kg=Decimal("90"), estado="extraviado")
        Encomienda(**self.datos_encomienda(peso_kg=Decimal("100"))).full_clean(exclude=["precio_envio"])

    def test_bus_sin_bodega_no_acepta_encomiendas(self):
        self.bus.capacidad_carga_kg = Decimal("0")
        self.bus.save()
        self.assertErrorEn(Encomienda(**self.datos_encomienda()), "peso_kg", "capacidad de carga")

    def test_editar_no_cuenta_su_propio_peso(self):
        encomienda = self.crear_encomienda(peso_kg=Decimal("100"))
        encomienda.full_clean()

    def test_transiciones_validas(self):
        encomienda = self.crear_encomienda()
        for estado in ("en_destino", "entregado"):
            encomienda.cambiar_estado(estado, self.usuario)
        encomienda.refresh_from_db()
        self.assertEqual(encomienda.estado, "entregado")
        self.assertEqual(encomienda.actualizado_por, self.usuario)
        self.assertEqual(encomienda.estados_siguientes, [])

    def test_transicion_invalida(self):
        encomienda = self.crear_encomienda()
        with self.assertRaisesMessage(ValidationError, "No se puede pasar de registrado a entregado"):
            encomienda.cambiar_estado("entregado", self.usuario)
        with self.assertRaisesMessage(ValidationError, "Estado no valido"):
            encomienda.cambiar_estado("perdido", self.usuario)
        encomienda.refresh_from_db()
        self.assertEqual(encomienda.estado, "registrado")

    def test_estado_final_no_retrocede_en_full_clean(self):
        encomienda = self.crear_encomienda(estado="extraviado")
        encomienda.estado = "en_destino"
        self.assertErrorEn(encomienda, "estado", "No se puede pasar de extraviado a en destino")

    def test_constraint_peso_positivo(self):
        with self.assertRaises(IntegrityError):
            self.crear_encomienda(peso_kg=Decimal("0"), precio_envio=Decimal("10"))

    def test_constraint_valor_declarado_no_negativo(self):
        with self.assertRaises(IntegrityError):
            self.crear_encomienda(valor_declarado=Decimal("-1"))


class PagoYComprobanteTests(EncomiendasTestCase):
    def setUp(self):
        self.encomienda = self.crear_encomienda()

    def test_pago_no_supera_precio(self):
        pago = PagoEncomienda(
            encomienda=self.encomienda, metodo="efectivo", monto=self.encomienda.precio_envio + Decimal("0.01")
        )
        with self.assertRaises(ValidationError) as contexto:
            pago.full_clean()
        self.assertIn("monto", contexto.exception.message_dict)

    def test_pago_no_efectivo_exige_referencia(self):
        pago = PagoEncomienda(encomienda=self.encomienda, metodo="qr", monto=Decimal("1"))
        with self.assertRaises(ValidationError) as contexto:
            pago.full_clean()
        self.assertIn("referencia_externa", contexto.exception.message_dict)

    def test_constraint_monto_positivo(self):
        with self.assertRaises(IntegrityError):
            PagoEncomienda.objects.create(encomienda=self.encomienda, metodo="efectivo", monto=Decimal("0"))

    def test_comprobante_genera_numero_unico(self):
        comprobante = ComprobanteEncomienda.objects.create(encomienda=self.encomienda)
        self.assertTrue(comprobante.numero_comprobante.startswith("CME-"))
        with self.assertRaises(IntegrityError):
            ComprobanteEncomienda.objects.create(encomienda=self.encomienda)
