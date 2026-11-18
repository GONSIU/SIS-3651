from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje

from .test_conductor import ConductorTestCase


class AbordajeTestCase(ConductorTestCase):
    def setUp(self):
        self.supervisor = Usuario.objects.create_user("super", rol="supervisor", terminal_asignado=self.la_paz)
        self.bus.crear_asientos()
        self.viaje_hoy = self.viaje(fecha_salida=self.hoy)
        self.viaje_hoy.save()
        self.viaje_hoy.crear_asientos_desde_bus()
        self.asientos = list(self.viaje_hoy.asientos_viaje.order_by("pk"))

    def pasaje(self, indice: int, estado: str = "pagado", **extra) -> Pasaje:
        asiento = self.asientos[indice]
        asiento.estado = {"pagado": "vendido", "reservado": "reservado"}.get(estado, "disponible")
        asiento.save()
        return Pasaje.objects.create(
            viaje=self.viaje_hoy, asiento_viaje=asiento, cliente_nombre=f"Pasajero {indice}",
            canal="ventanilla", precio=Decimal("50"), estado=estado, **extra,
        )

    def estado(self, pasaje: Pasaje) -> str:
        pasaje.refresh_from_db()
        return pasaje.estado


class RegistrarAbordajeTests(AbordajeTestCase):
    def test_marca_y_desmarca_solo_pasajes_pagados(self):
        subio, no_subio = self.pasaje(0), self.pasaje(1, abordo=True)
        reservado = self.pasaje(2, estado="reservado")
        self.assertEqual(self.viaje_hoy.registrar_abordaje([subio.pk, reservado.pk]), 1)
        for pasaje, esperado in ((subio, True), (no_subio, False), (reservado, False)):
            pasaje.refresh_from_db()
            self.assertEqual(pasaje.abordo, esperado)

    def test_ignora_pasajes_de_otro_viaje(self):
        otro = self.viaje(fecha_salida=self.manana, bus=self.otro_bus, conductor=self.otro_conductor)
        otro.save()
        self.otro_bus.crear_asientos()
        otro.crear_asientos_desde_bus()
        ajeno = Pasaje.objects.create(
            viaje=otro, asiento_viaje=otro.asientos_viaje.first(), cliente_nombre="Ajeno",
            canal="ventanilla", precio=Decimal("50"), estado="pagado",
        )
        self.assertEqual(self.viaje_hoy.registrar_abordaje([ajeno.pk]), 0)
        ajeno.refresh_from_db()
        self.assertFalse(ajeno.abordo)

    def test_no_se_marca_despues_de_salir(self):
        self.viaje_hoy.registrar_salida(self.supervisor)
        with self.assertRaises(ValidationError):
            self.viaje_hoy.registrar_abordaje([])


class SalidaCierraPasajesTests(AbordajeTestCase):
    def test_salida_reparte_usado_no_show_y_vencido(self):
        subio = self.pasaje(0, abordo=True)
        no_subio = self.pasaje(1)
        reserva = self.pasaje(2, estado="reservado", reservado_hasta=timezone.now())
        cancelado = self.pasaje(3, estado="cancelado")
        self.viaje_hoy.registrar_salida(self.supervisor)
        self.assertEqual(
            [self.estado(p) for p in (subio, no_subio, reserva, cancelado)],
            ["usado", "no_show", "vencido", "cancelado"],
        )
        reserva.asiento_viaje.refresh_from_db()
        self.assertEqual(reserva.asiento_viaje.estado, "disponible")

    def test_cancelar_el_viaje_no_toca_los_pasajes(self):
        pasaje = self.pasaje(0)
        self.viaje_hoy.cancelar(self.supervisor)
        self.assertEqual(self.estado(pasaje), "pagado")


class AbordajeViewTests(AbordajeTestCase):
    def url(self) -> str:
        return reverse("viajes:abordaje", args=[self.viaje_hoy.pk])

    def test_conductor_guarda_el_abordaje_de_su_viaje(self):
        pasaje = self.pasaje(0)
        self.client.force_login(self.conductor.usuario)
        respuesta = self.client.post(self.url(), {"abordo": [str(pasaje.pk), "abc"]}, follow=True)
        self.assertRedirects(respuesta, reverse("viajes:hoja_ruta", args=[self.viaje_hoy.pk]))
        pasaje.refresh_from_db()
        self.assertTrue(pasaje.abordo)

    def test_permisos(self):
        self.client.force_login(self.otro_conductor.usuario)
        self.assertEqual(self.client.post(self.url()).status_code, 404)
        self.client.force_login(Usuario.objects.create_user("venta", rol="ventanillero", terminal_asignado=self.la_paz))
        self.assertEqual(self.client.post(self.url()).status_code, 403)
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(self.url()).status_code, 405)

    def test_despues_de_salir_muestra_error(self):
        self.viaje_hoy.registrar_salida(self.supervisor)
        self.client.force_login(self.supervisor)
        respuesta = self.client.post(self.url(), follow=True)
        self.assertIn("antes de registrar la salida", " ".join(str(m) for m in respuesta.context["messages"]))

    def test_hoja_de_ruta_muestra_casillas_solo_antes_de_salir(self):
        self.pasaje(0)
        url_hoja = reverse("viajes:hoja_ruta", args=[self.viaje_hoy.pk])
        self.client.force_login(self.conductor.usuario)
        self.assertContains(self.client.get(url_hoja), 'name="abordo"')
        self.viaje_hoy.registrar_salida(self.supervisor)
        respuesta = self.client.get(url_hoja)
        self.assertNotContains(respuesta, 'name="abordo"')
        self.assertContains(respuesta, "No se presento")
