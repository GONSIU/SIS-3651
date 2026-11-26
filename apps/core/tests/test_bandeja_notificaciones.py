from decimal import Decimal

from django.urls import reverse

from apps.core.models import Notificacion
from apps.ventas.models import Pasaje
from apps.ventas.services import DatosPago, DatosPasajero, cobrar_saldo, registrar_venta
from apps.ventas.tests.test_reserva import PRECIO, ReservaTestCase
from apps.usuarios.models import Usuario


class AvisarTests(ReservaTestCase):
    def test_crea_un_aviso_por_usuario_e_ignora_repetidos_y_none(self):
        otro = Usuario.objects.create_user("otro", rol="cliente")
        creados = Notificacion.avisar([self.cliente.pk, self.cliente.pk, None, otro.pk], "T", "M")
        self.assertEqual(creados, 2)
        self.assertEqual(Notificacion.objects.count(), 2)

    def test_acepta_un_solo_id(self):
        Notificacion.avisar(self.cliente.pk, "T", "M", "/x/")
        aviso = Notificacion.objects.get()
        self.assertEqual((aviso.usuario, aviso.url, aviso.leida), (self.cliente, "/x/", False))

    def test_lista_vacia_no_crea_nada(self):
        self.assertEqual(Notificacion.avisar([], "T", "M"), 0)


class AvisosAutomaticosTests(ReservaTestCase):
    def avisos(self, usuario=None) -> list[str]:
        return list(Notificacion.objects.filter(usuario=usuario or self.cliente).values_list("titulo", flat=True))

    def test_reserva_con_anticipo_avisa_el_plazo_del_saldo(self):
        pasaje = self.reservar()
        aviso = Notificacion.objects.get(usuario=self.cliente)
        self.assertEqual(aviso.titulo, "Reserva confirmada")
        self.assertIn(pasaje.codigo_pasaje, aviso.mensaje)
        self.assertIn("Bs 70.00", aviso.mensaje)
        self.assertEqual(aviso.url, reverse("ventas:boleto", args=[pasaje.pk]))

    def test_reserva_pagada_completa(self):
        self.reservar(monto=PRECIO)
        self.assertEqual(self.avisos(), ["Reserva confirmada y pagada"])

    def test_cobrar_saldo_avisa_al_cliente(self):
        pasaje = self.reservar()
        cobrar_saldo(pasaje_id=pasaje.pk, pago=DatosPago(metodo="efectivo", monto=Decimal("70")), cobrado_por=self.vendedor)
        self.assertEqual(self.avisos()[0], "Saldo pagado")

    def test_venta_en_ventanilla_con_ci_de_cuenta_avisa(self):
        registrar_venta(
            viaje=self.viaje, asiento_viaje_id=self.viaje.asientos_viaje.first().pk,
            pasajero=DatosPasajero(nombre="Ana", ci=self.cliente.ci, telefono=""),
            precio=PRECIO, pago=DatosPago(metodo="efectivo", monto=PRECIO), vendido_por=self.vendedor,
        )
        self.assertEqual(self.avisos(), ["Compra de pasaje registrada"])

    def test_venta_sin_cuenta_no_crea_avisos(self):
        registrar_venta(
            viaje=self.viaje, asiento_viaje_id=self.viaje.asientos_viaje.first().pk,
            pasajero=DatosPasajero(nombre="Luis Mamani", ci="7654321", telefono=""),
            precio=PRECIO, pago=DatosPago(metodo="efectivo", monto=PRECIO), vendido_por=self.vendedor,
        )
        self.assertFalse(Notificacion.objects.exists())

    def test_retraso_y_cancelacion_avisan_solo_a_pasajes_vigentes(self):
        self.reservar()
        cancelado = self.reservar(comprador=Usuario.objects.create_user("bea", rol="cliente"))
        Pasaje.objects.filter(pk=cancelado.pk).update(estado="cancelado")
        Notificacion.objects.all().delete()

        self.viaje.marcar_retraso(15, self.vendedor)
        self.assertEqual(self.avisos(), ["Tu viaje tiene retraso"])
        self.assertIn("15 minutos", Notificacion.objects.get().mensaje)

        self.viaje.cancelar(self.vendedor)
        self.assertEqual(self.avisos()[0], "Tu viaje fue cancelado")
        self.assertEqual(Notificacion.objects.filter(usuario=cancelado.cliente).count(), 0)


class BandejaViewsTests(ReservaTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.otro = Usuario.objects.create_user("otro", rol="cliente")

    def setUp(self):
        self.client.force_login(self.cliente)
        self.mio = Notificacion.objects.create(usuario=self.cliente, titulo="Mio", mensaje="Hola", url="/ventas/mis-pasajes/")
        self.ajeno = Notificacion.objects.create(usuario=self.otro, titulo="Ajeno", mensaje="Secreto")

    def test_bandeja_muestra_solo_los_propios_y_el_contador(self):
        respuesta = self.client.get(reverse("core:notificaciones"))
        self.assertContains(respuesta, "Mio")
        self.assertNotContains(respuesta, "Ajeno")
        self.assertEqual(respuesta.context["sin_leer"], 1)

    def test_detalle_marca_como_leida(self):
        respuesta = self.client.get(reverse("core:notificacion", args=[self.mio.pk]))
        self.assertContains(respuesta, "Hola")
        self.mio.refresh_from_db()
        self.assertTrue(self.mio.leida)

    def test_aviso_ajeno_da_404_y_no_se_marca(self):
        self.assertEqual(self.client.get(reverse("core:notificacion", args=[self.ajeno.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(reverse("core:notificacion_eliminar", args=[self.ajeno.pk])).status_code, 404
        )
        self.ajeno.refresh_from_db()
        self.assertFalse(self.ajeno.leida)

    def test_eliminar(self):
        respuesta = self.client.post(reverse("core:notificacion_eliminar", args=[self.mio.pk]))
        self.assertRedirects(respuesta, reverse("core:notificaciones"))
        self.assertFalse(Notificacion.objects.filter(pk=self.mio.pk).exists())

    def test_eliminar_no_acepta_get(self):
        self.assertEqual(self.client.get(reverse("core:notificacion_eliminar", args=[self.mio.pk])).status_code, 405)

    def test_marcar_todas_leidas_solo_toca_las_propias(self):
        Notificacion.objects.create(usuario=self.cliente, titulo="Otra", mensaje="x")
        self.client.post(reverse("core:notificaciones_leidas"))
        self.assertFalse(Notificacion.objects.filter(usuario=self.cliente, leida=False).exists())
        self.ajeno.refresh_from_db()
        self.assertFalse(self.ajeno.leida)

    def test_contador_en_la_barra_publica(self):
        respuesta = self.client.get(reverse("ventas:mis_pasajes"))
        self.assertContains(respuesta, "Notificaciones (1 sin leer)")
        self.mio.marcar_leida()
        respuesta = self.client.get(reverse("ventas:mis_pasajes"))
        self.assertNotContains(respuesta, "sin leer)")

    def test_personal_no_entra_a_la_bandeja(self):
        self.client.force_login(self.vendedor)
        self.assertEqual(self.client.get(reverse("core:notificaciones")).status_code, 403)
