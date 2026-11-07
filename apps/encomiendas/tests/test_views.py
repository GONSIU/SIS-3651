from datetime import timedelta
from decimal import Decimal

from django.urls import reverse

from apps.encomiendas.models import Encomienda
from .base import EncomiendasTestCase


class NuevaEncomiendaViewTests(EncomiendasTestCase):
    def setUp(self):
        self.client.force_login(self.usuario)

    def registrar(self, **kwargs):
        datos = {
            "viaje": self.viaje.pk,
            "remitente_nombre": "Ana Perez",
            "remitente_ci": "1234567",
            "destinatario_nombre": "Luis Mamani",
            "destinatario_ci": "7654321",
            "descripcion_contenido": "Ropa",
            "peso_kg": "4.00",
            "metodo_pago": "efectivo",
        }
        return self.client.post(reverse("encomiendas:nueva"), {**datos, **kwargs})

    def test_exige_sesion(self):
        self.client.logout()
        respuesta = self.client.get(reverse("encomiendas:nueva"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("usuarios:login"), respuesta["Location"])

    def test_registro_valido_crea_pago_y_comprobante(self):
        respuesta = self.registrar(remitente_telefono="7123-4567", valor_declarado="200")
        encomienda = Encomienda.objects.get()
        self.assertRedirects(respuesta, reverse("encomiendas:guia", kwargs={"pk": encomienda.pk}))
        self.assertEqual(encomienda.registrado_por, self.usuario)
        self.assertEqual(encomienda.remitente_telefono, "71234567")
        self.assertEqual(encomienda.precio_envio, Decimal("22.00"))
        pago = encomienda.pagos.get()
        self.assertEqual(pago.monto, encomienda.precio_envio)
        self.assertTrue(encomienda.comprobante.numero_comprobante.startswith("CME-"))

    def test_metodo_no_efectivo_exige_referencia(self):
        respuesta = self.registrar(metodo_pago="tarjeta")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "necesita una referencia")
        self.assertFalse(Encomienda.objects.exists())

    def test_rechaza_exceso_de_carga(self):
        respuesta = self.registrar(peso_kg="150")
        self.assertContains(respuesta, "capacidad de carga")
        self.assertFalse(Encomienda.objects.exists())

    def test_no_ofrece_viajes_cancelados(self):
        cancelado = self.crear_viaje(fecha_salida=self.hoy + timedelta(days=2), estado="cancelado")
        respuesta = self.registrar(viaje=cancelado.pk)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("viaje", respuesta.context["form"].errors)
        self.assertFalse(Encomienda.objects.exists())

    def test_guia_muestra_datos(self):
        self.registrar()
        encomienda = Encomienda.objects.get()
        respuesta = self.client.get(reverse("encomiendas:guia", kwargs={"pk": encomienda.pk}))
        self.assertContains(respuesta, encomienda.codigo_guia)
        self.assertContains(respuesta, encomienda.comprobante.numero_comprobante)


class ListadoYEstadoViewTests(EncomiendasTestCase):
    def setUp(self):
        self.client.force_login(self.usuario)
        self.encomienda = self.crear_encomienda()

    def test_listado_filtra_por_estado(self):
        otra = self.crear_encomienda(destinatario_nombre="Rosa Quispe", estado="extraviado")
        respuesta = self.client.get(reverse("encomiendas:listado"), {"estado": "extraviado"})
        self.assertEqual(list(respuesta.context["encomiendas"]), [otra])

    def test_listado_busca_por_codigo(self):
        respuesta = self.client.get(reverse("encomiendas:listado"), {"q": self.encomienda.codigo_guia})
        self.assertContains(respuesta, self.encomienda.codigo_guia)

    def test_cambia_estado(self):
        respuesta = self.client.post(
            reverse("encomiendas:cambiar_estado", kwargs={"pk": self.encomienda.pk}), {"estado": "en_destino"}
        )
        self.assertRedirects(respuesta, reverse("encomiendas:listado"))
        self.encomienda.refresh_from_db()
        self.assertEqual(self.encomienda.estado, "en_destino")

    def test_rechaza_transicion_invalida(self):
        respuesta = self.client.post(
            reverse("encomiendas:cambiar_estado", kwargs={"pk": self.encomienda.pk}),
            {"estado": "entregado"},
            follow=True,
        )
        self.assertContains(respuesta, "No se puede pasar de registrado a entregado")
        self.encomienda.refresh_from_db()
        self.assertEqual(self.encomienda.estado, "registrado")

    def test_cambiar_estado_solo_por_post(self):
        respuesta = self.client.get(reverse("encomiendas:cambiar_estado", kwargs={"pk": self.encomienda.pk}))
        self.assertEqual(respuesta.status_code, 405)

    def test_formulario_nuevo_se_muestra(self):
        respuesta = self.client.get(reverse("encomiendas:nueva"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'enctype="multipart/form-data"')
        self.assertContains(respuesta, str(self.viaje))
