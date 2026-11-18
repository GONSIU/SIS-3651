from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.usuarios.models import Usuario
from apps.ventas.models import Pago, Pasaje
from apps.ventas.services import (
    CARGO_REPROGRAMACION,
    PLAZO_REPROGRAMACION,
    DatosPago,
    calcular_reprogramacion,
    reprogramar_pasaje,
)
from .test_reserva import PRECIO, ReservaTestCase

URL_LISTA = reverse("ventas:reprogramaciones")


class ReprogramacionTestCase(ReservaTestCase):
    def setUp(self):
        self.viaje_perdido = self.crear_viaje(fecha_salida=self.hoy - timedelta(days=1), estado="completado")
        asiento = self.viaje_perdido.asientos_viaje.first()
        asiento.estado = "vendido"
        asiento.save()
        self.original = Pasaje.objects.create(
            viaje=self.viaje_perdido, asiento_viaje=asiento, cliente=self.cliente,
            cliente_nombre="Ana María Pérez", cliente_ci="1234567", cliente_telefono="71234567",
            canal="online", precio=PRECIO, estado="no_show",
        )
        Pago.objects.create(pasaje=self.original, metodo="qr", monto=PRECIO, referencia_externa="QR-1")
        self.asiento_nuevo = self.viaje.asientos_viaje.order_by("pk").first()

    def reprogramar(self, precio=PRECIO, pago=None, asiento=None, viaje=None, original=None, **extra) -> Pasaje:
        return reprogramar_pasaje(
            original_id=(original or self.original).pk,
            viaje=viaje or self.viaje,
            asiento_viaje_id=(asiento or self.asiento_nuevo).pk,
            precio_viaje=precio,
            pago=pago or DatosPago(metodo="efectivo", monto=Decimal("0")),
            cobrado_por=self.vendedor,
            **extra,
        )


class ReprogramarServicioTests(ReprogramacionTestCase):
    def test_crea_el_pasaje_nuevo_con_credito_y_cargo(self):
        nuevo = self.reprogramar()
        self.original.refresh_from_db()
        nuevo.asiento_viaje.refresh_from_db()
        self.assertEqual((self.original.estado, nuevo.reprogramado_de), ("reprogramado", self.original))
        self.assertEqual((nuevo.estado, nuevo.asiento_viaje.estado), ("pagado", "vendido"))
        self.assertEqual(
            (nuevo.precio, nuevo.cargo_reprogramacion, nuevo.credito_reprogramacion),
            (PRECIO + CARGO_REPROGRAMACION, CARGO_REPROGRAMACION, PRECIO),
        )
        cobro = nuevo.pagos.get()
        self.assertEqual((cobro.monto, cobro.registrado_por), (CARGO_REPROGRAMACION, self.vendedor))
        self.assertEqual(nuevo.saldo, Decimal("0"))
        self.assertEqual(
            (nuevo.cliente, nuevo.cliente_nombre, nuevo.cliente_ci, nuevo.cliente_telefono),
            (self.cliente, "Ana María Pérez", "1234567", "71234567"),
        )

    def test_calculo_segun_el_precio_nuevo(self):
        casos = {
            Decimal("150.00"): (Decimal("100.00"), Decimal("70.00")),  # mas caro: paga diferencia + cargo
            PRECIO: (PRECIO, CARGO_REPROGRAMACION),  # igual: solo el cargo
            Decimal("60.00"): (Decimal("60.00"), CARGO_REPROGRAMACION),  # mas barato: no se devuelve nada
        }
        for precio, (credito, a_pagar) in casos.items():
            with self.subTest(precio=precio):
                calculo = calcular_reprogramacion(self.original, precio)
                self.assertEqual((calculo.credito, calculo.a_pagar), (credito, a_pagar))

    def test_solo_un_no_show_dentro_del_plazo(self):
        for estado in ("pagado", "usado", "vencido", "cancelado"):
            with self.subTest(estado=estado):
                Pasaje.objects.filter(pk=self.original.pk).update(estado=estado)
                with self.assertRaisesMessage(ValidationError, "no se presento"):
                    self.reprogramar()
        Pasaje.objects.filter(pk=self.original.pk).update(estado="no_show")
        tarde = self.viaje_perdido.salida_programada + PLAZO_REPROGRAMACION + timedelta(minutes=1)
        with self.assertRaisesMessage(ValidationError, "plazo"):
            self.reprogramar(ahora=tarde)

    def test_se_reprograma_una_sola_vez(self):
        nuevo = self.reprogramar()
        Pasaje.objects.filter(pk=nuevo.pk).update(estado="no_show")
        viaje_mas_tarde = self.crear_viaje(fecha_salida=self.hoy + timedelta(days=3))
        with self.assertRaisesMessage(ValidationError, "solo se reprograma una vez"):
            self.reprogramar(original=nuevo, viaje=viaje_mas_tarde, asiento=viaje_mas_tarde.asientos_viaje.first())

    def test_no_al_mismo_viaje_ni_a_un_asiento_ocupado(self):
        Pasaje.objects.filter(pk=self.original.pk).update(viaje=self.viaje)
        with self.assertRaisesMessage(ValidationError, "distinto"):
            self.reprogramar()
        Pasaje.objects.filter(pk=self.original.pk).update(viaje=self.viaje_perdido)
        self.viaje.asientos_viaje.filter(pk=self.asiento_nuevo.pk).update(estado="vendido")
        with self.assertRaisesMessage(ValidationError, "ya no esta disponible"):
            self.reprogramar()
        self.original.refresh_from_db()
        self.assertEqual(self.original.estado, "no_show")

    def test_error_en_el_pago_deshace_todo(self):
        with self.assertRaises(ValidationError):
            self.reprogramar(pago=DatosPago(metodo="qr", monto=Decimal("0")))  # sin referencia
        self.original.refresh_from_db()
        self.assertEqual(self.original.estado, "no_show")
        self.assertEqual(Pasaje.objects.count(), 1)


class ReprogramacionEnLaBaseTests(ReprogramacionTestCase):
    def test_la_base_impide_dos_reprogramaciones_del_mismo_pasaje(self):
        self.reprogramar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Pasaje.objects.create(
                viaje=self.viaje, asiento_viaje=self.viaje.asientos_viaje.order_by("pk")[1],
                cliente_nombre="Ana", canal="ventanilla", precio=Decimal("50"), reprogramado_de=self.original,
            )

    def test_el_credito_no_cubre_el_cargo(self):
        nuevo = self.reprogramar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Pasaje.objects.filter(pk=nuevo.pk).update(credito_reprogramacion=nuevo.precio)

    def test_los_pagos_descuentan_el_credito(self):
        nuevo = self.reprogramar()
        with self.assertRaises(ValidationError) as ctx:
            Pago(pasaje=nuevo, metodo="efectivo", monto=Decimal("1.00")).full_clean()
        self.assertIn("monto", ctx.exception.message_dict)


class ReprogramacionViewsTests(ReprogramacionTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("ventas:reprogramar", args=[self.original.pk])
        self.client.force_login(self.vendedor)

    def test_lista_y_busqueda(self):
        self.assertEqual(list(self.client.get(URL_LISTA).context["pasajes"]), [self.original])
        self.assertEqual(list(self.client.get(URL_LISTA, {"q": "1234567"}).context["pasajes"]), [self.original])
        self.assertEqual(list(self.client.get(URL_LISTA, {"q": "0000000"}).context["pasajes"]), [])

    def test_permisos(self):
        for rol in ("cliente", "conductor"):
            self.client.force_login(Usuario.objects.create_user(f"u_{rol}", rol=rol))
            for url in (URL_LISTA, self.url):
                with self.subTest(rol=rol, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)

    def test_elegir_viaje_muestra_el_calculo(self):
        respuesta = self.client.get(self.url)
        self.assertNotIn(self.viaje_perdido, respuesta.context["viajes"])
        self.assertIsNone(respuesta.context["calculo"])
        respuesta = self.client.get(self.url, {"viaje": self.viaje.pk})
        self.assertEqual(respuesta.context["calculo"].a_pagar, CARGO_REPROGRAMACION)
        self.assertContains(respuesta, 'name="asiento_viaje_id"')

    def test_pasaje_no_reprogramable_da_404(self):
        Pasaje.objects.filter(pk=self.original.pk).update(estado="usado")
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_viaje_perdido_fuera_del_plazo_no_aparece(self):
        dias = PLAZO_REPROGRAMACION.days + 1
        self.viaje_perdido.__class__.objects.filter(pk=self.viaje_perdido.pk).update(
            fecha_salida=self.hoy - timedelta(days=dias)
        )
        self.assertEqual(list(self.client.get(URL_LISTA).context["pasajes"]), [])
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_reprogramar_emite_el_boleto(self):
        datos = {
            "viaje_id": self.viaje.pk, "asiento_viaje_id": self.asiento_nuevo.pk, "precio": "100.00",
            "metodo_pago": "efectivo", "referencia": "", "nit": "", "razon_social": "",
        }
        respuesta = self.client.post(self.url, datos, follow=True)
        nuevo = Pasaje.objects.get(reprogramado_de=self.original)
        self.assertRedirects(respuesta, reverse("ventas:boleto", args=[nuevo.pk]))
        self.assertContains(respuesta, "Reprogramación del pasaje")
        self.assertContains(respuesta, self.original.codigo_pasaje)

    def test_sin_asiento_muestra_error(self):
        datos = {"viaje_id": self.viaje.pk, "precio": "100.00", "metodo_pago": "efectivo", "nit": "", "razon_social": ""}
        respuesta = self.client.post(self.url, datos)
        self.assertIn("asiento_viaje_id", respuesta.context["form"].errors)
        self.assertEqual(Pasaje.objects.count(), 1)
