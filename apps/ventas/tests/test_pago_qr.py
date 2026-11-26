from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.encomiendas.forms import EncomiendaForm
from apps.encomiendas.models import Encomienda, PagoEncomienda
from apps.usuarios.models import Usuario
from apps.ventas.forms import CobrarSaldoForm, ReprogramarForm, ReservaForm, VentaForm
from apps.ventas.qr import contenido_pago_qr
from apps.ventas.tests.base import VentasTestCase

URL = reverse("ventas:qr_pago")
REFERENCIA = "QR-AB12CD34"


class QrPagoViewTests(VentasTestCase):
    def setUp(self):
        self.client.force_login(self.vendedor)

    def test_devuelve_el_svg(self):
        respuesta = self.client.get(URL, {"monto": "40", "ref": REFERENCIA})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "image/svg+xml")
        self.assertIn(b"<svg", respuesta.content)

    def test_rechaza_monto_o_referencia_invalidos(self):
        for parametros in (
            {"monto": "abc", "ref": REFERENCIA},
            {"monto": "0", "ref": REFERENCIA},
            {"monto": "100000", "ref": REFERENCIA},
            {"monto": "40", "ref": "cualquier texto"},
            {"monto": "40", "ref": "qr-ab12cd34"},
            {},
        ):
            with self.subTest(parametros=parametros):
                self.assertEqual(self.client.get(URL, parametros).status_code, 400)

    def test_permisos(self):
        cliente = Usuario.objects.create_user("cli", rol="cliente")
        conductor = Usuario.objects.create_user("chofer", rol="conductor")
        for usuario, codigo in ((cliente, 200), (conductor, 403)):
            with self.subTest(rol=usuario.rol):
                self.client.force_login(usuario)
                self.assertEqual(self.client.get(URL, {"monto": "40", "ref": REFERENCIA}).status_code, codigo)
        self.client.logout()
        self.assertEqual(self.client.get(URL, {"monto": "40", "ref": REFERENCIA}).status_code, 302)

    def test_contenido_lleva_monto_y_referencia(self):
        texto = contenido_pago_qr(Decimal("40.5"), REFERENCIA)
        self.assertIn("REF:QR-AB12CD34", texto)
        self.assertIn("MONTO:40.50 BOB", texto)


class SinTarjetaTests(VentasTestCase):
    def test_ningun_formulario_ofrece_tarjeta(self):
        formularios = {
            "venta": VentaForm().fields["metodo_pago"],
            "reserva": ReservaForm(precio=Decimal("50"), monto_minimo=Decimal("15")).fields["metodo"],
            "cobro": CobrarSaldoForm().fields["metodo"],
            "reprogramar": ReprogramarForm().fields["metodo_pago"],
            "encomienda": EncomiendaForm().fields["metodo_pago"],
        }
        for nombre, campo in formularios.items():
            with self.subTest(formulario=nombre):
                metodos = {clave for clave, _ in campo.choices}
                self.assertNotIn("tarjeta", metodos)
                self.assertIn("qr", metodos)

    def test_pago_de_encomienda_con_tarjeta_se_rechaza(self):
        encomienda = Encomienda.objects.create(
            viaje=self.viaje, remitente_nombre="Ana Perez", remitente_ci="1234567",
            destinatario_nombre="Luis Mamani", destinatario_ci="7654321",
            descripcion_contenido="Ropa", peso_kg=Decimal("1"), registrado_por=self.vendedor,
        )
        pago = PagoEncomienda(encomienda=encomienda, metodo="tarjeta", monto=Decimal("1"), referencia_externa="X1")
        with self.assertRaises(ValidationError) as contexto:
            pago.full_clean()
        self.assertIn("metodo", contexto.exception.message_dict)

    def test_la_venta_muestra_el_bloque_qr(self):
        self.client.force_login(self.vendedor)
        respuesta = self.client.get(reverse("ventas:nueva_venta"), {"viaje": self.viaje.pk})
        self.assertContains(respuesta, "data-pago-qr")
        self.assertContains(respuesta, f'data-url="{URL}"')
        self.assertNotContains(respuesta, 'value="tarjeta"')
