from django.urls import reverse
from django.utils import timezone

from apps.core.models import Notificacion
from apps.incidencias.models import Incidencia
from apps.ventas.models import Pasaje
from .base import IncidenciasTestCase


class IncidenciasPersonalTests(IncidenciasTestCase):
    def setUp(self):
        self.client.force_login(self.supervisor)

    def test_registrar_incidencia(self):
        respuesta = self.client.post(
            reverse("incidencias:nueva"),
            {
                "categoria": "falla_mecanica", "titulo": "Llanta pinchada",
                "ocurrido_en": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "viaje": self.viaje.pk, "descripcion": "Cambio de llanta en el km 40.",
            },
        )
        incidencia = Incidencia.objects.get()
        self.assertRedirects(respuesta, reverse("incidencias:detalle", args=[incidencia.pk]))
        self.assertEqual((incidencia.reportado_por, incidencia.estado, incidencia.bus), (self.supervisor, "abierta", self.bus))

    def test_formulario_invalido_no_guarda(self):
        respuesta = self.client.post(reverse("incidencias:nueva"), {"categoria": "", "titulo": "", "descripcion": ""})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].errors)
        self.assertFalse(Incidencia.objects.exists())

    def test_listado_filtra_por_estado_categoria_y_busqueda(self):
        abierta = self.crear_incidencia(titulo="Motor recalentado")
        self.crear_reclamo(titulo="Aire acondicionado")
        resuelta = self.crear_incidencia(titulo="Frenos", estado="resuelta", resolucion="Listo")
        url = reverse("incidencias:listado")
        self.assertEqual(list(self.client.get(url, {"estado": "resuelta"}).context["incidencias"]), [resuelta])
        self.assertEqual(len(self.client.get(url, {"categoria": "reclamo"}).context["incidencias"]), 1)
        self.assertEqual(list(self.client.get(url, {"q": "recalentado"}).context["incidencias"]), [abierta])
        totales = self.client.get(url).context["totales"]
        self.assertEqual((totales["abiertas"], totales["resueltas"], totales["reclamos_pendientes"]), (2, 1, 1))

    def test_filtros_invalidos_se_ignoran(self):
        self.crear_incidencia()
        respuesta = self.client.get(reverse("incidencias:listado"), {"estado": "x", "categoria": "y"})
        self.assertEqual(len(respuesta.context["incidencias"]), 1)

    def test_detalle_y_resolver(self):
        reclamo = self.crear_reclamo()
        self.assertContains(self.client.get(reverse("incidencias:detalle", args=[reclamo.pk])), reclamo.codigo)
        url = reverse("incidencias:cambiar_estado", args=[reclamo.pk])
        respuesta = self.client.post(url, {"estado": "resuelta", "resolucion": "Reembolsamos el cargo."})
        self.assertRedirects(respuesta, reverse("incidencias:detalle", args=[reclamo.pk]))
        reclamo.refresh_from_db()
        self.assertEqual(reclamo.estado, "resuelta")
        self.assertTrue(Notificacion.objects.filter(usuario=self.cliente).exists())

    def test_resolver_sin_texto_muestra_error(self):
        incidencia = self.crear_incidencia()
        respuesta = self.client.post(
            reverse("incidencias:cambiar_estado", args=[incidencia.pk]), {"estado": "resuelta", "resolucion": ""}, follow=True
        )
        self.assertContains(respuesta, "Escribe la resolucion")
        incidencia.refresh_from_db()
        self.assertEqual(incidencia.estado, "abierta")

    def test_cambiar_estado_no_acepta_get(self):
        incidencia = self.crear_incidencia()
        self.assertEqual(self.client.get(reverse("incidencias:cambiar_estado", args=[incidencia.pk])).status_code, 405)


class ReclamosClienteTests(IncidenciasTestCase):
    def setUp(self):
        self.client.force_login(self.cliente)

    def test_enviar_reclamo_da_ticket_y_aviso(self):
        respuesta = self.client.post(
            reverse("incidencias:nuevo_reclamo"),
            {"categoria": "reclamo", "pasaje": self.pasaje.pk, "titulo": "Bus sucio", "descripcion": "Asientos sucios.", "calificacion": "2"},
            follow=True,
        )
        reclamo = Incidencia.objects.get()
        self.assertRedirects(respuesta, reverse("incidencias:mis_reclamos"))
        self.assertContains(respuesta, reclamo.codigo)
        self.assertEqual((reclamo.reportado_por, reclamo.calificacion, reclamo.viaje), (self.cliente, 2, self.viaje))
        self.assertEqual(Notificacion.objects.get(usuario=self.cliente).titulo, "Recibimos tu reclamo")

    def test_sugerencia_sin_pasaje_ni_calificacion(self):
        self.client.post(
            reverse("incidencias:nuevo_reclamo"),
            {"categoria": "sugerencia", "pasaje": "", "titulo": "Wifi", "descripcion": "Pongan wifi.", "calificacion": ""},
        )
        sugerencia = Incidencia.objects.get()
        self.assertEqual((sugerencia.categoria, sugerencia.pasaje, sugerencia.calificacion), ("sugerencia", None, None))

    def test_no_puede_reclamar_sobre_pasaje_ajeno(self):
        ajeno = Pasaje.objects.create(
            viaje=self.viaje, asiento_viaje=self.viaje.asientos_viaje.exclude(pk=self.asiento.pk).first(),
            cliente=self.otro_cliente, cliente_nombre="Beto", canal="online", precio=50, estado="pagado",
        )
        respuesta = self.client.post(
            reverse("incidencias:nuevo_reclamo"),
            {"categoria": "reclamo", "pasaje": ajeno.pk, "titulo": "X", "descripcion": "Y"},
        )
        self.assertIn("pasaje", respuesta.context["form"].errors)
        self.assertFalse(Incidencia.objects.exists())

    def test_cliente_no_elige_categorias_del_personal(self):
        respuesta = self.client.post(
            reverse("incidencias:nuevo_reclamo"), {"categoria": "falla_mecanica", "titulo": "X", "descripcion": "Y"}
        )
        self.assertIn("categoria", respuesta.context["form"].errors)

    def test_pasaje_preseleccionado_desde_mis_pasajes(self):
        respuesta = self.client.get(reverse("incidencias:nuevo_reclamo"), {"pasaje": self.pasaje.pk})
        self.assertEqual(respuesta.context["form"].initial["pasaje"], self.pasaje.pk)

    def test_mis_reclamos_muestra_solo_los_propios_y_la_respuesta(self):
        mio = self.crear_reclamo(titulo="Mi reclamo", estado="resuelta", resolucion="Respuesta oficial")
        self.crear_reclamo(titulo="Reclamo ajeno", reportado_por=self.otro_cliente)
        respuesta = self.client.get(reverse("incidencias:mis_reclamos"))
        self.assertEqual(list(respuesta.context["reclamos"]), [mio])
        self.assertContains(respuesta, "Respuesta oficial")
        self.assertNotContains(respuesta, "Reclamo ajeno")
