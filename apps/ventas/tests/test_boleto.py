from decimal import Decimal

from django.urls import reverse

from apps.usuarios.models import Usuario
from apps.ventas import services
from apps.ventas.qr import contenido_boleto_qr
from apps.ventas.tests.base import VentasTestCase


class BoletoTests(VentasTestCase):
    def setUp(self):
        self.horario.carril = 4
        self.horario.save(update_fields=["carril"])
        self.pasaje = services.registrar_venta(
            viaje=self.viaje, asiento_viaje_id=self.asiento.pk,
            pasajero=services.DatosPasajero(nombre="Begoña Nuñez", ci="1234567"),
            precio=Decimal("40"), pago=services.DatosPago(metodo="efectivo", monto=Decimal("40")),
            vendido_por=self.vendedor,
        )
        self.client.force_login(self.vendedor)

    def boleto(self):
        return self.client.get(reverse("ventas:boleto", args=[self.pasaje.pk]))

    def test_cabecera_pie_y_carril(self):
        respuesta = self.boleto()
        self.assertContains(respuesta, "img/logo-trans-naser.png")
        self.assertContains(respuesta, "Gracias por su preferencia")
        self.assertContains(respuesta, "NO REEMBOLSABLE")
        self.assertContains(respuesta, '<p class="text-gray-500">Carril</p><p class="font-semibold">4</p>', html=False)
        self.assertContains(respuesta, '<p class="font-semibold">08:00</p>', html=False)

    def test_qr_real_en_vez_del_dibujo(self):
        respuesta = self.boleto()
        self.assertContains(respuesta, 'src="data:image/svg+xml;base64,')
        self.assertNotContains(respuesta, "qr-placeholder")

    def test_contenido_del_qr(self):
        texto = contenido_boleto_qr(self.pasaje)
        for esperado in (self.pasaje.codigo_pasaje, "CARRIL 4", "La Paz - Oruro", "Begoña Nuñez CI 1234567",
                         "TOTAL: Bs 40.00", self.pasaje.comprobante.codigo_control):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, texto)

    def test_sin_carril_muestra_guion(self):
        self.horario.carril = None
        self.horario.save(update_fields=["carril"])
        self.assertContains(self.boleto(), '<p class="text-gray-500">Carril</p><p class="font-semibold">&mdash;</p>', html=False)
        self.assertNotIn("CARRIL", contenido_boleto_qr(self.pasaje))


class BoletoPdfTests(VentasTestCase):
    def setUp(self):
        self.cliente = Usuario.objects.create_user("ana", rol="cliente", ci="1234567", first_name="Ana")
        self.pasaje = services.registrar_venta(
            viaje=self.viaje, asiento_viaje_id=self.asiento.pk,
            pasajero=services.DatosPasajero(nombre="Ana", ci="1234567"),
            precio=Decimal("40"), pago=services.DatosPago(metodo="efectivo", monto=Decimal("40")),
            vendido_por=self.vendedor, facturacion=services.DatosFacturacion(nit="1234567", razon_social="Ana & Cia SRL"),
        )
        self.url = reverse("ventas:boleto_pdf", args=[self.pasaje.pk])

    def test_personal_descarga_el_pdf(self):
        self.client.force_login(self.vendedor)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertIn(f"boleto-{self.pasaje.codigo_pasaje}.pdf", respuesta["Content-Disposition"])
        self.assertTrue(respuesta.content.startswith(b"%PDF"))

    def test_cliente_descarga_el_suyo_y_no_el_ajeno(self):
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.force_login(Usuario.objects.create_user("otro", rol="cliente"))
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_comprobante_de_reserva_tambien_se_descarga(self):
        services.Pasaje.objects.filter(pk=self.pasaje.pk).update(
            estado="reservado", reservado_hasta=self.pasaje.viaje.salida_programada
        )
        self.client.force_login(self.vendedor)
        self.assertTrue(self.client.get(self.url).content.startswith(b"%PDF"))

    def test_boleto_html_enlaza_al_pdf(self):
        self.client.force_login(self.vendedor)
        self.assertContains(self.client.get(reverse("ventas:boleto", args=[self.pasaje.pk])), self.url)
