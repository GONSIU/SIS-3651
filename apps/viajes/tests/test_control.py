from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.encomiendas.forms import viajes_para_encomienda
from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje
from apps.viajes.models import Viaje
from apps.viajes.views import acciones_permitidas

from .test_conductor import ConductorTestCase


class ControlViajeModelTests(ConductorTestCase):
    def setUp(self):
        self.supervisor = Usuario.objects.create_user("super", rol="supervisor", terminal_asignado=self.la_paz)
        self.viaje_hoy = self.viaje(fecha_salida=self.hoy)
        self.viaje_hoy.save()

    def test_registrar_salida_calcula_el_retraso_real(self):
        momento = self.viaje_hoy.salida_programada + timedelta(minutes=25, seconds=40)
        self.viaje_hoy.registrar_salida(self.supervisor, momento=momento)
        self.viaje_hoy.refresh_from_db()
        self.assertEqual(self.viaje_hoy.estado, "en_curso")
        self.assertEqual(self.viaje_hoy.minutos_retraso, 25)
        self.assertEqual(self.viaje_hoy.hora_salida_real, momento)
        self.assertEqual(self.viaje_hoy.actualizado_por, self.supervisor)

    def test_salida_adelantada_no_tiene_retraso(self):
        momento = self.viaje_hoy.salida_programada - timedelta(minutes=10)
        self.viaje_hoy.registrar_salida(self.supervisor, momento=momento)
        self.assertEqual(self.viaje_hoy.minutos_retraso, 0)

    def test_no_se_registra_salida_antes_del_dia_del_viaje(self):
        viaje = self.viaje(fecha_salida=self.manana, bus=self.otro_bus, conductor=self.otro_conductor)
        viaje.save()
        with self.assertRaises(ValidationError):
            viaje.registrar_salida(self.supervisor)
        viaje.refresh_from_db()
        self.assertEqual(viaje.estado, "programado")

    def test_retraso_estimado_y_luego_salida_real(self):
        self.viaje_hoy.marcar_retraso(30, self.supervisor)
        self.assertEqual((self.viaje_hoy.estado, self.viaje_hoy.minutos_retraso), ("retrasado", 30))
        self.viaje_hoy.marcar_retraso(45, self.supervisor)
        self.assertEqual(self.viaje_hoy.minutos_retraso, 45)
        momento = self.viaje_hoy.salida_programada + timedelta(minutes=50)
        self.viaje_hoy.registrar_salida(self.supervisor, momento=momento)
        self.assertEqual(self.viaje_hoy.minutos_retraso, 50)

    def test_limites_del_retraso(self):
        for minutos in (0, -5, Viaje.MAX_MINUTOS_RETRASO + 1):
            with self.subTest(minutos=minutos), self.assertRaises(ValidationError):
                self.viaje_hoy.marcar_retraso(minutos, self.supervisor)
        self.viaje_hoy.marcar_retraso(Viaje.MAX_MINUTOS_RETRASO, self.supervisor)

    def test_cancelar_un_viaje_retrasado_borra_el_retraso(self):
        self.viaje_hoy.marcar_retraso(20, self.supervisor)
        self.viaje_hoy.cancelar(self.supervisor)
        self.viaje_hoy.refresh_from_db()
        self.assertEqual((self.viaje_hoy.estado, self.viaje_hoy.minutos_retraso), ("cancelado", 0))

    def test_registrar_llegada_guarda_la_hora_y_la_duracion(self):
        salida = self.viaje_hoy.salida_programada
        llegada = salida + timedelta(hours=3, minutes=20, seconds=30)
        self.viaje_hoy.registrar_salida(self.supervisor, momento=salida)
        self.viaje_hoy.registrar_llegada(self.supervisor, momento=llegada)
        self.viaje_hoy.refresh_from_db()
        self.assertEqual(self.viaje_hoy.estado, "completado")
        self.assertEqual(self.viaje_hoy.hora_llegada_real, llegada)
        self.assertEqual(self.viaje_hoy.duracion_real_minutos, 200)

    def test_llegada_anterior_a_la_salida_se_rechaza(self):
        salida = self.viaje_hoy.salida_programada
        self.viaje_hoy.registrar_salida(self.supervisor, momento=salida)
        with self.assertRaises(ValidationError):
            self.viaje_hoy.registrar_llegada(self.supervisor, momento=salida - timedelta(minutes=1))
        self.viaje_hoy.refresh_from_db()
        self.assertEqual((self.viaje_hoy.estado, self.viaje_hoy.hora_llegada_real), ("en_curso", None))

    def test_duracion_es_none_sin_salida_o_llegada(self):
        self.assertIsNone(self.viaje_hoy.duracion_real_minutos)
        self.viaje_hoy.registrar_salida(self.supervisor)
        self.assertIsNone(self.viaje_hoy.duracion_real_minutos)

    def test_constraint_de_llegada_en_la_base(self):
        salida = self.viaje_hoy.salida_programada
        consultas = Viaje.objects.filter(pk=self.viaje_hoy.pk)
        casos = {
            "llegada sin salida": {"hora_llegada_real": salida},
            "llegada antes de la salida": {"hora_salida_real": salida, "hora_llegada_real": salida - timedelta(minutes=5)},
        }
        for nombre, valores in casos.items():
            with self.subTest(caso=nombre), self.assertRaises(IntegrityError), transaction.atomic():
                consultas.update(**valores)

    def test_transiciones_no_permitidas(self):
        casos = {
            "programado": ("registrar_llegada",),
            "en_curso": ("marcar_retraso", "registrar_salida", "cancelar"),
            "completado": ("marcar_retraso", "registrar_salida", "registrar_llegada", "cancelar"),
            "cancelado": ("marcar_retraso", "registrar_salida", "registrar_llegada", "cancelar"),
        }
        for estado, metodos in casos.items():
            for metodo in metodos:
                with self.subTest(estado=estado, metodo=metodo):
                    Viaje.objects.filter(pk=self.viaje_hoy.pk).update(estado=estado, minutos_retraso=0)
                    viaje = Viaje.objects.get(pk=self.viaje_hoy.pk)
                    args = (10, self.supervisor) if metodo == "marcar_retraso" else (self.supervisor,)
                    with self.assertRaises(ValidationError):
                        getattr(viaje, metodo)(*args)
                    self.assertEqual(Viaje.objects.get(pk=viaje.pk).estado, estado)


class ControlViajeViewTests(ConductorTestCase):
    def setUp(self):
        self.supervisor = Usuario.objects.create_user("super", rol="supervisor", terminal_asignado=self.la_paz)
        self.viaje_hoy = self.viaje(fecha_salida=self.hoy)
        self.viaje_hoy.save()
        self.url = reverse("viajes:control", args=[self.viaje_hoy.pk])
        self.url_hoja = reverse("viajes:hoja_ruta", args=[self.viaje_hoy.pk])

    def post(self, accion: str, **extra):
        return self.client.post(self.url, {"accion": accion, **extra}, follow=True)

    def estado(self) -> str:
        return Viaje.objects.get(pk=self.viaje_hoy.pk).estado

    def mensajes(self, respuesta) -> list[str]:
        return [str(m) for m in respuesta.context["messages"]]

    def test_conductor_registra_la_salida_de_su_viaje(self):
        self.client.force_login(self.conductor.usuario)
        respuesta = self.post("salida")
        self.assertRedirects(respuesta, self.url_hoja)
        self.assertEqual(self.estado(), "en_curso")

    def test_conductor_registra_un_retraso(self):
        self.client.force_login(self.conductor.usuario)
        self.post("retraso", minutos="35")
        viaje = Viaje.objects.get(pk=self.viaje_hoy.pk)
        self.assertEqual((viaje.estado, viaje.minutos_retraso), ("retrasado", 35))

    def test_retraso_invalido_muestra_error_y_no_cambia_nada(self):
        self.client.force_login(self.conductor.usuario)
        for minutos in ("", "0", "abc", str(Viaje.MAX_MINUTOS_RETRASO + 1)):
            with self.subTest(minutos=minutos):
                respuesta = self.post("retraso", minutos=minutos)
                self.assertTrue(self.mensajes(respuesta))
                self.assertEqual(self.estado(), "programado")

    def test_conductor_no_puede_cancelar(self):
        self.client.force_login(self.conductor.usuario)
        self.assertEqual(self.client.post(self.url, {"accion": "cancelar"}).status_code, 403)
        self.assertEqual(self.estado(), "programado")

    def test_conductor_no_controla_un_viaje_ajeno(self):
        self.client.force_login(self.otro_conductor.usuario)
        self.assertEqual(self.client.post(self.url, {"accion": "salida"}).status_code, 404)
        self.assertEqual(self.estado(), "programado")

    def test_supervisor_cancela_cualquier_viaje(self):
        self.client.force_login(self.supervisor)
        self.post("cancelar")
        self.assertEqual(self.estado(), "cancelado")

    def test_transicion_invalida_muestra_error(self):
        self.client.force_login(self.supervisor)
        respuesta = self.post("llegada")
        self.assertIn("No se puede pasar de programado a completado.", self.mensajes(respuesta))
        self.assertEqual(self.estado(), "programado")

    def test_accion_desconocida(self):
        self.client.force_login(self.supervisor)
        respuesta = self.post("borrar")
        self.assertIn("Accion no valida.", self.mensajes(respuesta))

    def test_solo_acepta_post(self):
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_otros_roles_no_entran(self):
        for rol in ("cliente", "ventanillero"):
            with self.subTest(rol=rol):
                self.client.force_login(Usuario.objects.create_user(f"u_{rol}", rol=rol, terminal_asignado=self.la_paz))
                self.assertEqual(self.client.post(self.url, {"accion": "salida"}).status_code, 403)

    def test_acciones_que_muestra_la_hoja_de_ruta(self):
        self.assertEqual(acciones_permitidas(self.viaje_hoy, self.conductor.usuario), ["retraso", "salida"])
        self.assertEqual(
            acciones_permitidas(self.viaje_hoy, self.supervisor), ["retraso", "salida", "cancelar"]
        )
        self.viaje_hoy.registrar_salida(self.supervisor)
        self.assertEqual(acciones_permitidas(self.viaje_hoy, self.conductor.usuario), ["llegada"])
        self.viaje_hoy.registrar_llegada(self.supervisor)
        self.assertEqual(acciones_permitidas(self.viaje_hoy, self.supervisor), [])


class ViajeEnCursoNoVendeTests(ConductorTestCase):
    """Un bus que ya salio no vende pasajes ni recibe encomiendas."""

    def setUp(self):
        self.bus.crear_asientos()
        self.viaje_hoy = self.viaje(fecha_salida=self.hoy)
        self.viaje_hoy.save()
        self.viaje_hoy.crear_asientos_desde_bus()
        Viaje.objects.filter(pk=self.viaje_hoy.pk).update(estado="en_curso")
        self.viaje_hoy.refresh_from_db()

    def test_pasaje_en_viaje_en_curso_se_rechaza(self):
        pasaje = Pasaje(
            viaje=self.viaje_hoy, asiento_viaje=self.viaje_hoy.asientos_viaje.first(),
            cliente_nombre="Ana", canal="ventanilla", precio=Decimal("50"),
        )
        with self.assertRaises(ValidationError) as ctx:
            pasaje.full_clean()
        self.assertIn("viaje", ctx.exception.message_dict)

    def test_viaje_en_curso_no_aparece_en_la_venta(self):
        usuario = Usuario.objects.create_user("venta", rol="ventanillero", terminal_asignado=self.la_paz)
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("ventas:nueva_venta"))
        self.assertNotIn(self.viaje_hoy, respuesta.context["viajes"])

    def test_viaje_en_curso_no_recibe_encomiendas(self):
        self.assertNotIn(self.viaje_hoy, viajes_para_encomienda())
