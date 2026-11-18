from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.usuarios.models import Usuario
from apps.ventas.models import Comprobante, Pago, Pasaje
from apps.ventas.services import (
    DatosFacturacion,
    DatosPago,
    DatosPasajero,
    liberar_reservas_vencidas,
    registrar_venta,
)
from .base import VentasTestCase

PRECIO = Decimal("50.00")


class RegistrarVentaTests(VentasTestCase):
    def vender(self, asiento=None, pasajero=None, pago=None, facturacion=None, viaje=None) -> Pasaje:
        return registrar_venta(
            viaje=viaje or self.viaje,
            asiento_viaje_id=(asiento or self.asiento).pk,
            pasajero=pasajero or DatosPasajero(nombre="Ana Perez", ci="1234567", telefono="71234567"),
            precio=PRECIO,
            pago=pago or DatosPago(metodo="efectivo", monto=PRECIO),
            vendido_por=self.vendedor,
            facturacion=facturacion,
        )

    def comprobar_que_no_se_guardo_nada(self):
        self.assertFalse(Pasaje.objects.exists())
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(Comprobante.objects.exists())
        self.asiento.refresh_from_db()
        self.assertEqual(self.asiento.estado, "disponible")

    def test_venta_completa_con_recibo(self):
        pasaje = self.vender()
        self.asiento.refresh_from_db()
        self.assertEqual((pasaje.estado, pasaje.canal, self.asiento.estado), ("pagado", "ventanilla", "vendido"))
        self.assertEqual(pasaje.pagos.get().monto, PRECIO)
        self.assertEqual(pasaje.comprobante.tipo, "recibo")
        self.assertEqual(pasaje.vendido_por, self.vendedor)

    def test_con_datos_de_facturacion_emite_factura(self):
        pasaje = self.vender(facturacion=DatosFacturacion(nit="1020304050", razon_social="Empresa  SRL"))
        comprobante = pasaje.comprobante
        self.assertEqual(
            (comprobante.tipo, comprobante.nit_cliente, comprobante.razon_social_cliente),
            ("factura", "1020304050", "Empresa SRL"),
        )

    def test_facturacion_incompleta_no_guarda_nada(self):
        for facturacion in (DatosFacturacion(nit="1020304050"), DatosFacturacion(nit="12", razon_social="X")):
            with self.subTest(facturacion=facturacion), self.assertRaises(ValidationError):
                self.vender(facturacion=facturacion)
            self.comprobar_que_no_se_guardo_nada()

    def test_error_en_el_pago_deshace_toda_la_venta(self):
        with self.assertRaises(ValidationError):
            self.vender(pago=DatosPago(metodo="qr", monto=PRECIO))  # QR sin referencia
        self.comprobar_que_no_se_guardo_nada()

    def test_asiento_no_disponible(self):
        self.vender()
        with self.assertRaisesMessage(ValidationError, "ya no esta disponible"):
            self.vender(pasajero=DatosPasajero(nombre="Luis Mamani"))

    def test_asiento_de_otro_viaje(self):
        otro_viaje = self.crear_viaje(fecha_salida=self.hoy + timedelta(days=2))
        with self.assertRaisesMessage(ValidationError, "no pertenece"):
            self.vender(asiento=otro_viaje.asientos_viaje.first())

    def test_ci_de_una_cuenta_usa_el_nombre_registrado(self):
        cliente = Usuario.objects.create_user("ana", rol="cliente", ci="1234567", first_name="Ana", last_name="Perez")
        pasaje = self.vender(pasajero=DatosPasajero(nombre="Otro Nombre", ci="1234567"))
        self.assertEqual((pasaje.cliente, pasaje.cliente_nombre), (cliente, "Ana Perez"))

    def test_cuenta_sin_nombre_conserva_el_nombre_escrito(self):
        cliente = Usuario.objects.create_user("sin_nombre", rol="cliente", ci="1234567")
        pasaje = self.vender(pasajero=DatosPasajero(nombre="Luis Mamani", ci="1234567"))
        self.assertEqual((pasaje.cliente, pasaje.cliente_nombre), (cliente, "Luis Mamani"))


class AsientoConHistorialTests(VentasTestCase):
    def pasaje(self, estado: str, **kwargs) -> Pasaje:
        return Pasaje.objects.create(
            viaje=self.viaje, asiento_viaje=self.asiento, cliente_nombre="Ana",
            canal="online", precio=PRECIO, estado=estado, **kwargs,
        )

    def test_dos_pasajes_activos_en_el_mismo_asiento_no_se_permiten(self):
        self.pasaje("reservado")
        for estado in ("reservado", "pagado", "usado"):
            with self.subTest(estado=estado), self.assertRaises(IntegrityError), transaction.atomic():
                self.pasaje(estado)

    def test_un_pasaje_inactivo_no_bloquea_el_asiento(self):
        self.pasaje("vencido")
        self.pasaje("cancelado")
        self.pasaje("pagado")
        self.assertEqual(self.asiento.pasajes.count(), 3)

    def test_se_revende_un_asiento_liberado(self):
        self.pasaje("vencido")
        pasaje = registrar_venta(
            viaje=self.viaje, asiento_viaje_id=self.asiento.pk,
            pasajero=DatosPasajero(nombre="Luis Mamani"), precio=PRECIO,
            pago=DatosPago(metodo="efectivo", monto=PRECIO), vendido_por=self.vendedor,
        )
        self.assertEqual(pasaje.estado, "pagado")
        self.assertEqual(sorted(self.asiento.pasajes.values_list("estado", flat=True)), ["pagado", "vencido"])


class LiberarReservasVencidasTests(VentasTestCase):
    def setUp(self):
        self.ahora = timezone.now()
        self.asientos = list(self.viaje.asientos_viaje.all())

    def reservar(self, indice: int, reservado_hasta, estado="reservado", viaje=None) -> Pasaje:
        asiento = (viaje.asientos_viaje.first() if viaje else self.asientos[indice])
        asiento.estado = "reservado" if estado == "reservado" else "vendido"
        asiento.save()
        return Pasaje.objects.create(
            viaje=viaje or self.viaje, asiento_viaje=asiento, cliente_nombre="Ana", canal="online",
            precio=PRECIO, estado=estado, reservado_hasta=reservado_hasta,
        )

    def estado(self, pasaje: Pasaje) -> tuple[str, str]:
        pasaje.refresh_from_db()
        pasaje.asiento_viaje.refresh_from_db()
        return pasaje.estado, pasaje.asiento_viaje.estado

    def test_vence_solo_las_reservas_con_plazo_pasado(self):
        vencida = self.reservar(0, self.ahora - timedelta(minutes=1))
        vigente = self.reservar(1, self.ahora + timedelta(hours=1))
        sin_plazo = self.reservar(2, None)
        pagada = self.reservar(3, self.ahora - timedelta(minutes=1), estado="pagado")

        self.assertEqual(liberar_reservas_vencidas(ahora=self.ahora), 1)
        self.assertEqual(self.estado(vencida), ("vencido", "disponible"))
        self.assertEqual(self.estado(vigente), ("reservado", "reservado"))
        self.assertEqual(self.estado(sin_plazo), ("reservado", "reservado"))
        self.assertEqual(self.estado(pagada), ("pagado", "vendido"))

    def test_filtra_por_viaje(self):
        otro_viaje = self.crear_viaje(fecha_salida=self.hoy + timedelta(days=2))
        de_este = self.reservar(0, self.ahora - timedelta(minutes=1))
        del_otro = self.reservar(0, self.ahora - timedelta(minutes=1), viaje=otro_viaje)
        self.assertEqual(liberar_reservas_vencidas(viaje=self.viaje, ahora=self.ahora), 1)
        self.assertEqual(self.estado(de_este)[0], "vencido")
        self.assertEqual(self.estado(del_otro)[0], "reservado")

    def test_sin_reservas_vencidas_no_hace_nada(self):
        self.assertEqual(liberar_reservas_vencidas(ahora=self.ahora), 0)

    def test_la_venta_libera_antes_de_vender(self):
        self.reservar(0, self.ahora - timedelta(minutes=1))
        pasaje = registrar_venta(
            viaje=self.viaje, asiento_viaje_id=self.asientos[0].pk,
            pasajero=DatosPasajero(nombre="Luis Mamani"), precio=PRECIO,
            pago=DatosPago(metodo="efectivo", monto=PRECIO), vendido_por=self.vendedor,
        )
        self.assertEqual(pasaje.estado, "pagado")

    def test_comando_liberar_reservas(self):
        self.reservar(0, timezone.now() - timedelta(minutes=1))
        salida = StringIO()
        call_command("liberar_reservas", stdout=salida)
        self.assertIn("Reservas vencidas: 1.", salida.getvalue())


class NombrePasajeroYComprobanteTests(VentasTestCase):
    def test_el_nombre_del_pasajero_tiene_prioridad_sobre_la_cuenta(self):
        cuenta = Usuario.objects.create_user("ana", first_name="Ana", last_name="Perez")
        pasaje = Pasaje(cliente=cuenta, cliente_nombre="Luis Perez")
        self.assertEqual(pasaje.nombre_pasajero, "Luis Perez")
        pasaje.cliente_nombre = ""
        self.assertEqual(pasaje.nombre_pasajero, "Ana Perez")
        self.assertEqual(Pasaje().nombre_pasajero, "—")

    def test_factura_sin_nit_se_rechaza(self):
        pasaje = Pasaje.objects.create(
            viaje=self.viaje, asiento_viaje=self.asiento, cliente_nombre="Ana", canal="ventanilla", precio=PRECIO
        )
        with self.assertRaises(ValidationError):
            Comprobante(pasaje=pasaje, tipo="factura").full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Comprobante.objects.create(pasaje=pasaje, tipo="factura")
