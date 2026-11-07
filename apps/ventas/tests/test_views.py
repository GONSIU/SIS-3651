from datetime import timedelta

from django.urls import reverse

from apps.ventas.models import Pago, Pasaje
from apps.viajes.models import Viaje
from .base import VentasTestCase


class NuevaVentaViewTests(VentasTestCase):
    def vender(self, **kwargs):
        datos = {
            "viaje_id": self.viaje.pk,
            "asiento_viaje_id": self.asiento.pk,
            "cliente_nombre": "Ana Perez",
            "precio": "50.00",
            "metodo_pago": "efectivo",
        }
        return self.client.post(reverse("ventas:nueva_venta"), {**datos, **kwargs})

    def test_venta_valida(self):
        respuesta = self.vender(cliente_ci="1234567-1b")
        pasaje = Pasaje.objects.get()
        self.assertRedirects(respuesta, reverse("ventas:boleto", kwargs={"pk": pasaje.pk}))
        self.assertEqual(pasaje.estado, "pagado")
        self.assertEqual(pasaje.cliente_ci, "1234567-1B")
        self.asiento.refresh_from_db()
        self.assertEqual(self.asiento.estado, "vendido")
        self.assertEqual(pasaje.pagos.count(), 1)
        self.assertTrue(hasattr(pasaje, "comprobante"))

    def test_normaliza_antes_de_validar(self):
        respuesta = self.vender(cliente_nombre="Ana   Perez", telefono="7123-4567")
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Pasaje.objects.get().cliente_nombre, "Ana Perez")

    def test_no_vende_en_viaje_cancelado(self):
        Viaje.objects.filter(pk=self.viaje.pk).update(estado="cancelado")
        respuesta = self.vender()
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se puede vender")
        self.assertFalse(Pasaje.objects.exists())
        self.asiento.refresh_from_db()
        self.assertEqual(self.asiento.estado, "disponible")

    def test_no_vende_en_viaje_pasado(self):
        Viaje.objects.filter(pk=self.viaje.pk).update(fecha_salida=self.hoy - timedelta(days=1))
        respuesta = self.vender()
        self.assertContains(respuesta, "la fecha de salida ya paso")
        self.assertFalse(Pasaje.objects.exists())

    def test_no_vende_un_asiento_ocupado(self):
        self.asiento.estado = "vendido"
        self.asiento.save()
        respuesta = self.vender()
        self.assertContains(respuesta, "Ese asiento ya no")
        self.assertFalse(Pasaje.objects.exists())

    def test_asiento_de_otro_viaje_devuelve_404(self):
        otro_viaje = self.crear_viaje(fecha_salida=self.hoy + timedelta(days=2))
        respuesta = self.vender(asiento_viaje_id=otro_viaje.asientos_viaje.first().pk)
        self.assertEqual(respuesta.status_code, 404)
        self.assertFalse(Pasaje.objects.exists())

    def test_muestra_los_errores_de_cada_campo(self):
        casos = [
            ("cliente_nombre", "as12"),
            ("cliente_ci", "asca"),
            ("telefono", "abc"),
            ("precio", "0"),
        ]
        for campo, valor in casos:
            with self.subTest(campo=campo):
                respuesta = self.vender(**{campo: valor})
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn(campo, respuesta.context["form"].errors)
                self.assertContains(respuesta, respuesta.context["form"].errors[campo][0])
                self.assertFalse(Pasaje.objects.exists())

    def test_metodo_electronico_exige_referencia(self):
        respuesta = self.vender(metodo_pago="qr")
        self.assertIn("referencia_externa", respuesta.context["form"].errors)
        self.assertContains(respuesta, "necesita una referencia")
        self.assertFalse(Pasaje.objects.exists())

    def test_guarda_la_referencia_del_pago(self):
        self.vender(metodo_pago="qr", referencia_externa="QR-123")
        pago = Pago.objects.get()
        self.assertEqual(pago.referencia_externa, "QR-123")
        pago.full_clean()

    def test_no_lista_viajes_cancelados_ni_completados(self):
        cancelado = self.crear_viaje(fecha_salida=self.hoy + timedelta(days=2), estado="cancelado")
        completado = self.crear_viaje(fecha_salida=self.hoy + timedelta(days=3), estado="completado")
        viajes = self.client.get(reverse("ventas:nueva_venta")).context["viajes"]
        self.assertIn(self.viaje, viajes)
        self.assertNotIn(cancelado, viajes)
        self.assertNotIn(completado, viajes)
