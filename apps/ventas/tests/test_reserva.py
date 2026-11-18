from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.flota.models import Bus
from apps.rutas.models import Ruta
from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje
from apps.ventas.services import (
    CIERRE_RESERVA_ONLINE,
    MAX_PASAJES_ONLINE_POR_VIAJE,
    MAX_RESERVAS_PENDIENTES,
    DatosFacturacion,
    DatosPago,
    DatosPasajero,
    cancelar_reserva,
    liberar_reservas_vencidas,
    monto_minimo_anticipo,
    registrar_reserva,
)
from .base import VentasTestCase

PRECIO = Decimal("100.00")


class ReservaTestCase(VentasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Ruta.objects.filter(pk=cls.ruta.pk).update(precio_base=PRECIO)
        cls.ruta.refresh_from_db()
        cls.viaje.refresh_from_db()
        cls.cliente = Usuario.objects.create_user(
            "ana", rol="cliente", ci="1234567", first_name="Ana María", last_name="Pérez",
            telefono="71234567", password="clave-segura-123",
        )

    def asientos(self):
        return list(self.viaje.asientos_viaje.order_by("pk"))

    def reservar(self, monto=Decimal("30.00"), asiento=None, pasajero=None, comprador=None, viaje=None, **extra):
        viaje = viaje or self.viaje
        return registrar_reserva(
            viaje=viaje,
            asiento_viaje_id=(asiento or viaje.asientos_viaje.filter(estado="disponible").first()).pk,
            comprador=comprador or self.cliente,
            pasajero=pasajero or DatosPasajero(nombre="Luis Mamani", ci="7654321", telefono="69998888"),
            pago=extra.pop("pago", None) or DatosPago(metodo="qr", monto=monto, referencia="QR-123"),
            **extra,
        )


class RegistrarReservaTests(ReservaTestCase):
    def test_anticipo_parcial_deja_la_reserva_pendiente(self):
        pasaje = self.reservar()
        pasaje.asiento_viaje.refresh_from_db()
        self.assertEqual((pasaje.estado, pasaje.asiento_viaje.estado), ("reservado", "reservado"))
        self.assertEqual(pasaje.reservado_hasta, self.viaje.salida_programada - CIERRE_RESERVA_ONLINE)
        self.assertEqual((pasaje.total_pagado, pasaje.saldo), (Decimal("30.00"), Decimal("70.00")))
        self.assertEqual((pasaje.canal, pasaje.cliente, pasaje.vendido_por), ("online", self.cliente, None))
        self.assertTrue(hasattr(pasaje, "comprobante"))

    def test_pago_total_deja_el_pasaje_pagado(self):
        pasaje = self.reservar(monto=PRECIO, facturacion=DatosFacturacion(nit="1020304050", razon_social="Empresa SRL"))
        pasaje.asiento_viaje.refresh_from_db()
        self.assertEqual((pasaje.estado, pasaje.asiento_viaje.estado, pasaje.reservado_hasta), ("pagado", "vendido", None))
        self.assertEqual((pasaje.saldo, pasaje.comprobante.tipo), (Decimal("0"), "factura"))

    def test_monto_fuera_de_rango_no_guarda_nada(self):
        for monto in (Decimal("29.99"), Decimal("100.01")):
            with self.subTest(monto=monto), self.assertRaises(ValidationError) as ctx:
                self.reservar(monto=monto)
            self.assertIn("monto", ctx.exception.message_dict)
        self.assertFalse(Pasaje.objects.exists())

    def test_online_no_acepta_efectivo(self):
        with self.assertRaises(ValidationError) as ctx:
            self.reservar(pago=DatosPago(metodo="efectivo", monto=PRECIO))
        self.assertIn("metodo", ctx.exception.message_dict)

    def test_metodo_sin_referencia_no_guarda_nada(self):
        with self.assertRaises(ValidationError):
            self.reservar(pago=DatosPago(metodo="qr", monto=PRECIO))
        self.assertFalse(Pasaje.objects.exists())
        self.assertFalse(self.viaje.asientos_viaje.exclude(estado="disponible").exists())

    def test_viaje_sin_precio_o_cerrado(self):
        Ruta.objects.filter(pk=self.ruta.pk).update(precio_base=None)
        self.viaje.ruta.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "no se puede reservar"):
            self.reservar()
        Ruta.objects.filter(pk=self.ruta.pk).update(precio_base=PRECIO)
        self.viaje.ruta.refresh_from_db()
        tarde = self.viaje.salida_programada - timedelta(minutes=30)
        with self.assertRaisesMessage(ValidationError, "ya cerro"):
            self.reservar(ahora=tarde)

    def test_asiento_tomado(self):
        asiento = self.asientos()[0]
        self.reservar(asiento=asiento)
        with self.assertRaisesMessage(ValidationError, "ya no esta disponible"):
            self.reservar(asiento=asiento)

    def test_anticipo_minimo_redondea_hacia_arriba(self):
        self.assertEqual(monto_minimo_anticipo(Decimal("100.01")), Decimal("30.01"))
        self.assertEqual(monto_minimo_anticipo(Decimal("100.00")), Decimal("30.00"))


class NombreContraCuentaTests(ReservaTestCase):
    def test_ci_de_una_cuenta_exige_el_mismo_nombre_sin_revelarlo(self):
        with self.assertRaises(ValidationError) as ctx:
            self.reservar(pasajero=DatosPasajero(nombre="Otra Persona", ci="1234567", telefono="71234567"))
        mensaje = " ".join(ctx.exception.messages)
        self.assertIn("no coincide", mensaje)
        self.assertNotIn("Ana", mensaje)
        self.assertFalse(Pasaje.objects.exists())

    def test_coincide_sin_importar_tildes_mayusculas_ni_espacios(self):
        pasaje = self.reservar(pasajero=DatosPasajero(nombre="ana  maria PEREZ", ci="1234567", telefono="71234567"))
        self.assertEqual(pasaje.cliente_nombre, "Ana María Pérez")

    def test_ci_sin_cuenta_acepta_el_nombre_escrito(self):
        pasaje = self.reservar()
        self.assertEqual(pasaje.cliente_nombre, "Luis Mamani")


class LimitesTests(ReservaTestCase):
    def test_maximo_de_pasajes_por_viaje(self):
        # Bus de 10 asientos: el de la base tiene 4 y se llenaria antes que el limite.
        bus = Bus.objects.create(placa="9999ZZZ", nombre_tipo="Cama", capacidad_pasajeros=10, capacidad_carga_kg=0)
        bus.crear_asientos()
        viaje = self.crear_viaje(bus=bus, fecha_salida=self.hoy + timedelta(days=2))
        for _ in range(MAX_PASAJES_ONLINE_POR_VIAJE - 1):
            self.reservar(viaje=viaje)
        self.reservar(viaje=viaje, monto=PRECIO)  # los pagados tambien cuentan en el viaje
        self.reservar()  # en otro viaje si se permite
        with self.assertRaisesMessage(ValidationError, "maximo por cuenta"):
            self.reservar(viaje=viaje)

    def test_maximo_de_reservas_pendientes(self):
        viajes = [self.crear_viaje(fecha_salida=self.hoy + timedelta(days=d)) for d in range(2, 4)]
        for _ in range(MAX_RESERVAS_PENDIENTES // 2):
            for viaje in viajes:
                self.reservar(viaje=viaje)
        with self.assertRaisesMessage(ValidationError, "sin pagar por completo"):
            self.reservar()

    def test_reservas_vencidas_o_canceladas_no_cuentan(self):
        for _ in range(MAX_PASAJES_ONLINE_POR_VIAJE):
            cancelar_reserva(self.reservar(), self.cliente)
        self.reservar()


class CancelarYVencerTests(ReservaTestCase):
    def test_cancelar_libera_el_asiento_y_conserva_el_anticipo(self):
        pasaje = self.reservar()
        cancelar_reserva(pasaje, self.cliente)
        pasaje.refresh_from_db()
        pasaje.asiento_viaje.refresh_from_db()
        self.assertEqual((pasaje.estado, pasaje.asiento_viaje.estado), ("cancelado", "disponible"))
        self.assertEqual(pasaje.total_pagado, Decimal("30.00"))

    def test_no_se_cancela_un_pasaje_pagado(self):
        pasaje = self.reservar(monto=PRECIO)
        with self.assertRaises(ValidationError):
            cancelar_reserva(pasaje, self.cliente)

    def test_reserva_vencida_libera_el_asiento(self):
        pasaje = self.reservar()
        liberar_reservas_vencidas(ahora=pasaje.reservado_hasta + timedelta(minutes=1))
        pasaje.refresh_from_db()
        pasaje.asiento_viaje.refresh_from_db()
        self.assertEqual((pasaje.estado, pasaje.asiento_viaje.estado), ("vencido", "disponible"))


class ReservarViewTests(ReservaTestCase):
    def setUp(self):
        self.asiento_libre = self.asientos()[0]
        self.url = reverse("ventas:reservar", args=[self.viaje.pk])

    def datos(self, **cambios) -> dict:
        datos = {
            "asiento": self.asiento_libre.pk, "cliente_nombre": "Luis Mamani", "cliente_ci": "7654321",
            "cliente_telefono": "6999-8888", "nit": "", "razon_social": "", "monto": "30.00",
            "metodo": "qr", "referencia": "QR-123", "acepta_condiciones": "on",
        }
        datos.update(cambios)
        return datos

    def test_sin_sesion_va_al_login_y_el_personal_no_entra(self):
        respuesta = self.client.get(self.url, {"asiento": self.asiento_libre.pk})
        self.assertTrue(respuesta["Location"].startswith(reverse("usuarios:login")))
        self.client.force_login(self.vendedor)
        self.assertEqual(self.client.get(self.url, {"asiento": self.asiento_libre.pk}).status_code, 403)

    def test_formulario_precargado_con_la_cuenta(self):
        self.client.force_login(self.cliente)
        respuesta = self.client.get(self.url, {"asiento": self.asiento_libre.pk})
        iniciales = respuesta.context["form"].initial
        self.assertEqual((iniciales["cliente_nombre"], iniciales["cliente_ci"]), ("Ana María Pérez", "1234567"))
        self.assertEqual(iniciales["monto"], Decimal("30.00"))

    def test_sin_asiento_o_asiento_ocupado_vuelve_al_mapa(self):
        self.client.force_login(self.cliente)
        self.viaje.asientos_viaje.filter(pk=self.asiento_libre.pk).update(estado="vendido")
        for parametros in ({}, {"asiento": "abc"}, {"asiento": self.asiento_libre.pk}):
            with self.subTest(parametros=parametros):
                respuesta = self.client.get(self.url, parametros)
                self.assertRedirects(respuesta, reverse("ventas:viaje_publico", args=[self.viaje.pk]))

    def test_reserva_con_anticipo_muestra_comprobante(self):
        self.client.force_login(self.cliente)
        respuesta = self.client.post(self.url, self.datos(), follow=True)
        pasaje = Pasaje.objects.get()
        self.assertRedirects(respuesta, reverse("ventas:boleto", args=[pasaje.pk]))
        self.assertContains(respuesta, "COMPROBANTE DE RESERVA")
        self.assertContains(respuesta, "SALDO PENDIENTE")
        self.assertEqual(pasaje.cliente_telefono, "69998888")

    def test_pago_total_muestra_el_boleto(self):
        self.client.force_login(self.cliente)
        respuesta = self.client.post(self.url, self.datos(monto="100.00"), follow=True)
        self.assertContains(respuesta, "BOLETO DE VIAJE")
        self.assertContains(respuesta, "Venta online")

    def test_errores_del_formulario(self):
        self.client.force_login(self.cliente)
        casos = {
            "acepta_condiciones": self.datos(acepta_condiciones=""),
            "monto": self.datos(monto="10"),
            "razon_social": self.datos(nit="1020304050"),
            "cliente_telefono": self.datos(cliente_telefono=""),
        }
        for campo, datos in casos.items():
            with self.subTest(campo=campo):
                respuesta = self.client.post(self.url, datos)
                self.assertIn(campo, respuesta.context["form"].errors)
        self.assertFalse(Pasaje.objects.exists())

    def test_error_del_servicio_va_al_campo(self):
        self.client.force_login(self.cliente)
        respuesta = self.client.post(self.url, self.datos(cliente_nombre="Otra Persona", cliente_ci="1234567"))
        self.assertIn("cliente_nombre", respuesta.context["form"].errors)

    def test_viaje_cerrado_da_404(self):
        self.client.force_login(self.cliente)
        Ruta.objects.filter(pk=self.ruta.pk).update(precio_base=None)
        self.assertEqual(self.client.get(self.url, {"asiento": self.asiento_libre.pk}).status_code, 404)


class MisPasajesViewTests(ReservaTestCase):
    def test_lista_solo_los_pasajes_de_la_cuenta(self):
        propio = self.reservar()
        otra = Usuario.objects.create_user("otra", rol="cliente", ci="5555555")
        ajeno = self.reservar(comprador=otra)
        self.client.force_login(self.cliente)
        pasajes = list(self.client.get(reverse("ventas:mis_pasajes")).context["pasajes"])
        self.assertEqual(pasajes, [propio])
        self.assertNotEqual(ajeno, propio)

    def test_cancelar_una_reserva_propia(self):
        pasaje = self.reservar()
        self.client.force_login(self.cliente)
        respuesta = self.client.post(reverse("ventas:cancelar_reserva", args=[pasaje.pk]))
        self.assertRedirects(respuesta, reverse("ventas:mis_pasajes"))
        pasaje.refresh_from_db()
        self.assertEqual(pasaje.estado, "cancelado")

    def test_no_cancela_la_reserva_de_otro(self):
        otra = Usuario.objects.create_user("otra", rol="cliente", ci="5555555")
        pasaje = self.reservar(comprador=otra)
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.post(reverse("ventas:cancelar_reserva", args=[pasaje.pk])).status_code, 404)
        pasaje.refresh_from_db()
        self.assertEqual(pasaje.estado, "reservado")

    def test_cancelar_solo_por_post(self):
        pasaje = self.reservar()
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(reverse("ventas:cancelar_reserva", args=[pasaje.pk])).status_code, 405)


class MapaYLoginDelClienteTests(ReservaTestCase):
    def test_el_cliente_puede_elegir_asiento_en_el_mapa(self):
        url = reverse("ventas:viaje_publico", args=[self.viaje.pk])
        # type="radio" solo aparece en un mapa seleccionable (el script menciona el nombre).
        self.assertNotContains(self.client.get(url), 'type="radio"')
        self.client.force_login(self.cliente)
        respuesta = self.client.get(url)
        self.assertContains(respuesta, 'name="asiento" type="radio"')
        self.assertContains(respuesta, reverse("ventas:reservar", args=[self.viaje.pk]))

    def test_cliente_inicia_sesion_en_mis_pasajes(self):
        respuesta = self.client.post(reverse("usuarios:login"), {"username": "ana", "password": "clave-segura-123"})
        self.assertRedirects(respuesta, reverse("ventas:mis_pasajes"))
