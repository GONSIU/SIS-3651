from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Notificacion
from apps.incidencias.models import Incidencia
from .base import IncidenciasTestCase


class IncidenciaModeloTests(IncidenciasTestCase):
    def test_codigo_segun_quien_la_origina(self):
        self.assertTrue(self.crear_incidencia().codigo.startswith("INC-"))
        self.assertTrue(self.crear_reclamo().codigo.startswith("RCL-"))

    def test_viaje_y_bus_se_deducen_del_pasaje(self):
        reclamo = self.crear_reclamo(pasaje=self.pasaje)
        self.assertEqual((reclamo.viaje, reclamo.bus), (self.viaje, self.bus))

    def test_bus_se_deduce_del_viaje(self):
        self.assertEqual(self.crear_incidencia(viaje=self.viaje).bus, self.bus)

    def test_nueva_empieza_abierta(self):
        incidencia = Incidencia(
            categoria="otro", titulo="X", descripcion="Y", reportado_por=self.supervisor, estado="en_revision"
        )
        with self.assertRaises(ValidationError) as error:
            incidencia.full_clean()
        self.assertIn("estado", error.exception.message_dict)

    def test_fecha_del_suceso_no_puede_ser_futura(self):
        incidencia = Incidencia(
            categoria="otro", titulo="X", descripcion="Y", reportado_por=self.supervisor,
            ocurrido_en=timezone.now() + timedelta(hours=2),
        )
        with self.assertRaises(ValidationError) as error:
            incidencia.full_clean()
        self.assertIn("ocurrido_en", error.exception.message_dict)

    def test_calificacion_solo_en_reclamos(self):
        incidencia = Incidencia(categoria="otro", titulo="X", descripcion="Y", reportado_por=self.supervisor, calificacion=3)
        with self.assertRaises(ValidationError) as error:
            incidencia.full_clean()
        self.assertIn("calificacion", error.exception.message_dict)

    def test_calificacion_fuera_de_rango_la_rechaza_la_base(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear_reclamo(calificacion=6)

    def test_resuelta_sin_resolucion_la_rechaza_la_base(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear_incidencia(estado="resuelta", resolucion="")

    def test_viaje_distinto_del_pasaje(self):
        otro_viaje = self.crear_viaje(fecha_salida=self.hoy + timedelta(days=3))
        reclamo = Incidencia(
            categoria="reclamo", titulo="X", descripcion="Y", reportado_por=self.cliente,
            pasaje=self.pasaje, viaje=otro_viaje,
        )
        with self.assertRaises(ValidationError) as error:
            reclamo.full_clean()
        self.assertIn("viaje", error.exception.message_dict)

    def test_normaliza_titulo(self):
        incidencia = Incidencia(categoria="otro", titulo="  Falla   de  motor ", descripcion=" Y ", reportado_por=self.supervisor)
        incidencia.full_clean()
        self.assertEqual((incidencia.titulo, incidencia.descripcion), ("Falla de motor", "Y"))


class CambiarEstadoTests(IncidenciasTestCase):
    def test_flujo_completo(self):
        incidencia = self.crear_incidencia()
        incidencia.cambiar_estado("en_revision", self.supervisor)
        incidencia.cambiar_estado("resuelta", self.supervisor, "  Se cambio la pastilla de freno. ")
        incidencia.refresh_from_db()
        self.assertEqual(incidencia.estado, "resuelta")
        self.assertEqual(incidencia.resolucion, "Se cambio la pastilla de freno.")
        self.assertEqual(incidencia.resuelta_por, self.supervisor)
        self.assertIsNotNone(incidencia.resuelta_en)

    def test_resolver_exige_resolucion(self):
        incidencia = self.crear_incidencia()
        with self.assertRaises(ValidationError):
            incidencia.cambiar_estado("resuelta", self.supervisor, "   ")
        incidencia.refresh_from_db()
        self.assertEqual(incidencia.estado, "abierta")

    def test_resuelta_es_final(self):
        incidencia = self.crear_incidencia()
        incidencia.cambiar_estado("resuelta", self.supervisor, "Listo")
        for estado in ("abierta", "en_revision", "resuelta"):
            with self.subTest(estado=estado), self.assertRaises(ValidationError):
                incidencia.cambiar_estado(estado, self.supervisor, "Otra vez")

    def test_estado_desconocido(self):
        with self.assertRaises(ValidationError):
            self.crear_incidencia().cambiar_estado("borrada", self.supervisor)

    def test_avisa_al_cliente_en_cada_cambio(self):
        reclamo = self.crear_reclamo()
        reclamo.cambiar_estado("en_revision", self.supervisor)
        reclamo.cambiar_estado("resuelta", self.supervisor, "Te pedimos disculpas.")
        avisos = list(Notificacion.objects.filter(usuario=self.cliente).order_by("pk"))
        self.assertEqual([a.titulo for a in avisos], ["Tu reclamo esta en revision", "Tu reclamo fue respondido"])
        self.assertIn("Te pedimos disculpas.", avisos[1].mensaje)
        self.assertEqual(avisos[1].url, reverse("incidencias:mis_reclamos"))

    def test_incidencia_del_personal_no_crea_avisos(self):
        self.crear_incidencia().cambiar_estado("resuelta", self.supervisor, "Listo")
        self.assertFalse(Notificacion.objects.exists())
