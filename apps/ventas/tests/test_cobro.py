from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje
from apps.ventas.services import DatosFacturacion, DatosPago, cobrar_saldo
from .test_reserva import PRECIO, ReservaTestCase

URL_PENDIENTES = reverse("ventas:reservas_pendientes")


class CobrarSaldoServicioTests(ReservaTestCase):
    def setUp(self):
        self.reserva = self.reservar(facturacion=DatosFacturacion(nit="1020304050", razon_social="Empresa SRL"))

    def cobrar(self, pago=None, **extra) -> Pasaje:
        return cobrar_saldo(
            pasaje_id=self.reserva.pk, pago=pago or DatosPago(metodo="efectivo", monto=Decimal("70.00")),
            cobrado_por=self.vendedor, **extra,
        )

    def test_cobra_el_saldo_y_valida_el_boleto(self):
        pasaje = self.cobrar()
        pasaje.refresh_from_db()
        pasaje.asiento_viaje.refresh_from_db()
        self.assertEqual((pasaje.estado, pasaje.asiento_viaje.estado, pasaje.reservado_hasta), ("pagado", "vendido", None))
        self.assertEqual((pasaje.total_pagado, pasaje.saldo), (PRECIO, Decimal("0")))
        saldo = pasaje.pagos.get(registrado_por=self.vendedor)
        self.assertEqual(saldo.monto, Decimal("70.00"))
        # Cobrar el saldo no convierte al ventanillero en el vendedor (reporte de desempeno).
        self.assertIsNone(pasaje.vendido_por)
        self.assertEqual(pasaje.actualizado_por, self.vendedor)

    def test_el_monto_es_siempre_el_saldo_del_servidor(self):
        pasaje = self.cobrar(pago=DatosPago(metodo="efectivo", monto=Decimal("1.00")))
        self.assertEqual(pasaje.total_pagado, PRECIO)

    def test_sin_facturacion_conserva_la_del_reserva(self):
        pasaje = self.cobrar()
        self.assertEqual((pasaje.comprobante.tipo, pasaje.comprobante.nit_cliente), ("factura", "1020304050"))

    def test_facturacion_nueva_reemplaza_la_anterior(self):
        pasaje = self.cobrar(facturacion=DatosFacturacion())
        pasaje.comprobante.refresh_from_db()
        self.assertEqual((pasaje.comprobante.tipo, pasaje.comprobante.nit_cliente), ("recibo", ""))

    def test_no_cobra_una_reserva_vencida(self):
        tarde = self.reserva.reservado_hasta + timedelta(minutes=1)
        with self.assertRaisesMessage(ValidationError, "vencio"):
            self.cobrar(ahora=tarde)
        self.assertEqual(self.reserva.pagos.count(), 1)

    def test_no_cobra_dos_veces_ni_lo_cancelado(self):
        self.cobrar()
        with self.assertRaisesMessage(ValidationError, "ya no esta pendiente"):
            self.cobrar()
        otra = self.reservar()
        Pasaje.objects.filter(pk=otra.pk).update(estado="cancelado")
        with self.assertRaisesMessage(ValidationError, "ya no esta pendiente"):
            cobrar_saldo(pasaje_id=otra.pk, pago=DatosPago(metodo="efectivo", monto=Decimal("1")), cobrado_por=self.vendedor)

    def test_error_en_el_pago_no_cambia_nada(self):
        with self.assertRaises(ValidationError):
            self.cobrar(pago=DatosPago(metodo="qr", monto=Decimal("70.00")))  # sin referencia
        self.reserva.refresh_from_db()
        self.assertEqual((self.reserva.estado, self.reserva.pagos.count()), ("reservado", 1))

    def test_quien_registra_cada_pago(self):
        self.assertIsNone(self.reserva.pagos.get().registrado_por)  # pago en linea


class ReservasPendientesViewTests(ReservaTestCase):
    def setUp(self):
        self.reserva = self.reservar()
        self.client.force_login(self.vendedor)

    def test_lista_solo_las_pendientes_vigentes(self):
        pagada = self.reservar(monto=PRECIO)
        vencida = self.reservar()
        Pasaje.objects.filter(pk=vencida.pk).update(reservado_hasta=timezone.now() - timedelta(minutes=1))
        reservas = list(self.client.get(URL_PENDIENTES).context["reservas"])
        self.assertEqual(reservas, [self.reserva])
        self.assertNotIn(pagada, reservas)

    def test_busca_por_codigo_o_ci(self):
        for consulta in (self.reserva.codigo_pasaje.lower(), "7654321", " 765 4321 "):
            with self.subTest(q=consulta):
                reservas = list(self.client.get(URL_PENDIENTES, {"q": consulta}).context["reservas"])
                self.assertEqual(reservas, [self.reserva])
        self.assertEqual(list(self.client.get(URL_PENDIENTES, {"q": "0000000"}).context["reservas"]), [])

    def test_busca_por_ci_de_la_cuenta_compradora(self):
        reservas = list(self.client.get(URL_PENDIENTES, {"q": "1234567"}).context["reservas"])
        self.assertEqual(reservas, [self.reserva])

    def test_permisos(self):
        url_cobrar = reverse("ventas:cobrar_saldo", args=[self.reserva.pk])
        for rol in ("cliente", "conductor"):
            self.client.force_login(Usuario.objects.create_user(f"u_{rol}", rol=rol))
            for url in (URL_PENDIENTES, url_cobrar):
                with self.subTest(rol=rol, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)


class CobrarSaldoViewTests(ReservaTestCase):
    def setUp(self):
        self.reserva = self.reservar(facturacion=DatosFacturacion(nit="1020304050", razon_social="Empresa SRL"))
        self.url = reverse("ventas:cobrar_saldo", args=[self.reserva.pk])
        self.client.force_login(self.vendedor)

    def test_precarga_la_facturacion_de_la_reserva(self):
        iniciales = self.client.get(self.url).context["form"].initial
        self.assertEqual((iniciales["nit"], iniciales["razon_social"]), ("1020304050", "Empresa SRL"))

    def test_cobrar_emite_el_boleto(self):
        datos = {"metodo": "efectivo", "referencia": "", "nit": "1020304050", "razon_social": "Empresa SRL"}
        respuesta = self.client.post(self.url, datos, follow=True)
        self.assertRedirects(respuesta, reverse("ventas:boleto", args=[self.reserva.pk]))
        self.assertContains(respuesta, "BOLETO DE VIAJE")
        self.assertNotContains(respuesta, "SALDO PENDIENTE")

    def test_metodo_sin_referencia(self):
        respuesta = self.client.post(self.url, {"metodo": "qr", "referencia": "", "nit": "", "razon_social": ""})
        self.assertIn("referencia", respuesta.context["form"].errors)
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.estado, "reservado")

    def test_reserva_vencida_o_pagada_da_404(self):
        Pasaje.objects.filter(pk=self.reserva.pk).update(reservado_hasta=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.client.get(self.url).status_code, 404)


class BuscarPasajeroViewTests(ReservaTestCase):
    url = reverse("ventas:buscar_pasajero")

    def test_personal_obtiene_los_datos(self):
        self.client.force_login(self.vendedor)
        datos = self.client.get(self.url, {"ci": "1234567"}).json()
        self.assertEqual(
            datos, {"valido": True, "encontrado": True, "nombre": "Ana María Pérez", "telefono": "71234567", "tiene_cuenta": True}
        )

    def test_ci_invalido_o_sin_registros(self):
        self.client.force_login(self.vendedor)
        self.assertEqual(self.client.get(self.url, {"ci": "12"}).json(), {"valido": False, "encontrado": False})
        self.assertEqual(self.client.get(self.url, {"ci": "9999999"}).json(), {"valido": True, "encontrado": False})

    def test_un_cliente_no_puede_consultar_cis(self):
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(self.url, {"ci": "1234567"}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {"ci": "1234567"}).status_code, 302)

    def test_respuesta_sin_cache(self):
        self.client.force_login(self.vendedor)
        self.assertIn("no-cache", self.client.get(self.url, {"ci": "1234567"})["Cache-Control"])


class VentaVentanillaConFacturaTests(ReservaTestCase):
    def setUp(self):
        self.client.force_login(self.vendedor)

    def vender(self, **extra):
        datos = {
            "viaje_id": self.viaje.pk, "asiento_viaje_id": self.asiento.pk, "cliente_nombre": "Luis Mamani",
            "precio": "100.00", "metodo_pago": "efectivo", "nit": "", "razon_social": "",
        }
        datos.update(extra)
        return self.client.post(reverse("ventas:nueva_venta"), datos)

    def test_venta_con_factura(self):
        self.vender(nit="1020304050", razon_social="Empresa SRL")
        pasaje = Pasaje.objects.get()
        self.assertEqual((pasaje.comprobante.tipo, pasaje.comprobante.nit_cliente), ("factura", "1020304050"))
        self.assertEqual(pasaje.pagos.get().registrado_por, self.vendedor)

    def test_facturacion_incompleta(self):
        respuesta = self.vender(nit="1020304050")
        self.assertIn("razon_social", respuesta.context["form"].errors)
        self.assertFalse(Pasaje.objects.exists())

    def test_la_pagina_incluye_el_llenado_automatico(self):
        respuesta = self.client.get(reverse("ventas:nueva_venta"), {"viaje": self.viaje.pk})
        self.assertContains(respuesta, reverse("ventas:buscar_pasajero"))
