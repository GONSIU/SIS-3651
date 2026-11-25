from datetime import time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.flota.models import Bus
from apps.rutas.forms import HorarioForm, RutaForm
from apps.rutas.models import DIAS_VALIDOS, Horario, Ruta, Terminal
from apps.usuarios.models import Usuario
from apps.viajes.forms import ViajeForm
from apps.viajes.models import Viaje

TODOS_LOS_DIAS = ",".join(DIAS_VALIDOS)


class GestionRutasTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.la_paz = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        cls.oruro = Terminal.objects.create(nombre="Central", ciudad="Oruro")
        cls.potosi = Terminal.objects.create(nombre="Nueva", ciudad="Potosi")
        cls.bus = Bus.objects.create(
            placa="1234ABC", nombre_tipo="Semicama", capacidad_pasajeros=10, capacidad_carga_kg=0
        )
        cls.supervisor = Usuario.objects.create_user("super", rol="supervisor", terminal_asignado=cls.la_paz)
        cls.hoy = timezone.localdate()
        cls.manana = cls.hoy + timedelta(days=1)

    def setUp(self):
        self.ruta = Ruta.objects.create(origen=self.la_paz, destino=self.oruro, distancia_km=Decimal("230"))
        self.horario = Horario.objects.create(ruta=self.ruta, hora_salida=time(8), dias_semana=TODOS_LOS_DIAS)
        self.client.force_login(self.supervisor)

    def programar(self, fecha=None, estado="programado", horario=None) -> Viaje:
        # objects.create no ejecuta clean(): permite viajes pasados y en cualquier estado.
        return Viaje.objects.create(
            ruta=self.ruta, horario=horario or self.horario, bus=self.bus,
            fecha_salida=fecha or self.manana, estado=estado,
        )

    def datos_ruta(self, **cambios) -> dict:
        datos = {
            "origen": self.ruta.origen_id, "destino": self.ruta.destino_id,
            "distancia_km": "230", "duracion_minutos": "180", "precio_base": "45.50", "activa": "on",
        }
        datos.update(cambios)
        return datos

    def datos_horario(self, **cambios) -> dict:
        datos = {"ruta": self.ruta.pk, "hora_salida": "08:00", "dias_semana": TODOS_LOS_DIAS}
        datos.update(cambios)
        return datos

    def mensajes(self, respuesta) -> list[str]:
        return [str(m) for m in respuesta.context["messages"]]


class EditarRutaTests(GestionRutasTestCase):
    def url(self) -> str:
        return reverse("rutas:editar", args=[self.ruta.pk])

    def test_edita_datos_y_precio_base(self):
        respuesta = self.client.post(self.url(), self.datos_ruta(), follow=True)
        self.assertRedirects(respuesta, reverse("rutas:listado"))
        self.ruta.refresh_from_db()
        self.assertEqual((self.ruta.duracion_minutos, self.ruta.precio_base), (180, Decimal("45.50")))

    def test_sin_viajes_se_pueden_cambiar_los_terminales(self):
        self.client.post(self.url(), self.datos_ruta(destino=self.potosi.pk))
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.destino, self.potosi)

    def test_con_viajes_los_terminales_no_cambian(self):
        self.programar()
        form = RutaForm(instance=self.ruta)
        self.assertTrue(form.fields["origen"].disabled and form.fields["destino"].disabled)
        # Aunque el POST traiga otro destino, Django usa el valor guardado.
        self.client.post(self.url(), self.datos_ruta(destino=self.potosi.pk))
        self.ruta.refresh_from_db()
        self.assertEqual(self.ruta.destino, self.oruro)
        self.assertEqual(self.ruta.precio_base, Decimal("45.50"))

    def test_precio_base_invalido(self):
        for precio in ("0", "-5"):
            with self.subTest(precio=precio):
                form = RutaForm(data=self.datos_ruta(precio_base=precio), instance=self.ruta)
                self.assertIn("precio_base", form.errors)

    def test_precio_base_es_opcional(self):
        form = RutaForm(data=self.datos_ruta(precio_base=""), instance=self.ruta)
        self.assertTrue(form.is_valid(), form.errors)

    def test_constraint_de_precio_en_la_base(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ruta.objects.filter(pk=self.ruta.pk).update(precio_base=Decimal("0"))


class EliminarRutaTests(GestionRutasTestCase):
    def url(self) -> str:
        return reverse("rutas:eliminar", args=[self.ruta.pk])

    def test_ruta_sin_viajes_se_elimina_con_sus_horarios(self):
        self.assertFalse(self.client.get(self.url()).context["bloqueado"])
        respuesta = self.client.post(self.url(), follow=True)
        self.assertRedirects(respuesta, reverse("rutas:listado"))
        self.assertFalse(Ruta.objects.filter(pk=self.ruta.pk).exists())
        self.assertFalse(Horario.objects.filter(pk=self.horario.pk).exists())

    def test_ruta_con_viajes_no_se_elimina(self):
        self.programar()
        self.assertTrue(self.client.get(self.url()).context["bloqueado"])
        respuesta = self.client.post(self.url(), follow=True)
        self.assertTrue(Ruta.objects.filter(pk=self.ruta.pk).exists())
        self.assertIn("tiene viajes", self.mensajes(respuesta)[0])


class ActivarRutaTests(GestionRutasTestCase):
    def url(self) -> str:
        return reverse("rutas:activar", args=[self.ruta.pk])

    def test_alterna_el_estado(self):
        self.client.post(self.url())
        self.ruta.refresh_from_db()
        self.assertFalse(self.ruta.activa)
        self.client.post(self.url())
        self.ruta.refresh_from_db()
        self.assertTrue(self.ruta.activa)

    def test_avisa_cuantos_viajes_pendientes_siguen_vigentes(self):
        self.programar()
        self.programar(fecha=self.hoy - timedelta(days=2), estado="completado")
        respuesta = self.client.post(self.url(), follow=True)
        self.assertIn("Sus 1 viaje(s) pendientes siguen vigentes", self.mensajes(respuesta)[0])

    def test_solo_acepta_post(self):
        self.assertEqual(self.client.get(self.url()).status_code, 405)


class RutaYHorarioInactivosTests(GestionRutasTestCase):
    def test_formulario_de_viaje_excluye_inactivos(self):
        otro = Horario.objects.create(ruta=self.ruta, hora_salida=time(14), dias_semana=TODOS_LOS_DIAS, activo=False)
        horarios = set(ViajeForm().fields["horario"].queryset)
        self.assertIn(self.horario, horarios)
        self.assertNotIn(otro, horarios)
        Ruta.objects.filter(pk=self.ruta.pk).update(activa=False)
        self.assertFalse(ViajeForm().fields["horario"].queryset.exists())

    def test_no_se_crea_viaje_en_ruta_u_horario_inactivo(self):
        casos = {"ruta": Ruta.objects.filter(pk=self.ruta.pk), "horario": Horario.objects.filter(pk=self.horario.pk)}
        for campo, consulta in casos.items():
            with self.subTest(campo=campo):
                consulta.update(**{"activa" if campo == "ruta" else "activo": False})
                viaje = Viaje(ruta=Ruta.objects.get(pk=self.ruta.pk), horario=Horario.objects.get(pk=self.horario.pk),
                              bus=self.bus, fecha_salida=self.manana)
                with self.assertRaises(ValidationError) as ctx:
                    viaje.full_clean()
                self.assertIn(campo, ctx.exception.message_dict)
                consulta.update(**{"activa" if campo == "ruta" else "activo": True})

    def test_viaje_existente_se_edita_aunque_se_desactive_la_ruta(self):
        viaje = self.programar()
        Ruta.objects.filter(pk=self.ruta.pk).update(activa=False)
        Horario.objects.filter(pk=self.horario.pk).update(activo=False)
        Viaje.objects.get(pk=viaje.pk).full_clean()


class EditarHorarioTests(GestionRutasTestCase):
    def url(self) -> str:
        return reverse("rutas:horario_editar", args=[self.horario.pk])

    def test_sin_viajes_cambia_la_hora(self):
        respuesta = self.client.post(self.url(), self.datos_horario(hora_salida="09:30"))
        self.assertRedirects(respuesta, reverse("rutas:horarios", kwargs={"ruta_id": self.ruta.pk}))
        self.horario.refresh_from_db()
        self.assertEqual(self.horario.hora_salida, time(9, 30))

    def test_no_cambia_de_ruta(self):
        otra = Ruta.objects.create(origen=self.oruro, destino=self.la_paz)
        self.client.post(self.url(), self.datos_horario(ruta=otra.pk))
        self.horario.refresh_from_db()
        self.assertEqual(self.horario.ruta, self.ruta)

    def test_con_viajes_la_hora_no_cambia(self):
        self.programar()
        self.assertTrue(HorarioForm(instance=self.horario).fields["hora_salida"].disabled)
        self.client.post(self.url(), self.datos_horario(hora_salida="09:30", dias_semana=TODOS_LOS_DIAS))
        self.horario.refresh_from_db()
        self.assertEqual(self.horario.hora_salida, time(8))

    def test_no_quita_un_dia_con_viajes_futuros(self):
        viaje = self.programar()
        sin_ese_dia = [d for d in DIAS_VALIDOS if d != DIAS_VALIDOS[viaje.fecha_salida.weekday()]]
        form = HorarioForm(data=self.datos_horario(dias_semana=",".join(sin_ese_dia)), instance=self.horario)
        self.assertIn("dias_semana", form.errors)

    def test_quitar_un_dia_con_viajes_pasados_o_cancelados_se_permite(self):
        pasado = self.programar(fecha=self.hoy - timedelta(days=7), estado="completado")
        cancelado = self.programar(fecha=self.manana, estado="cancelado")
        dias_quitados = {DIAS_VALIDOS[v.fecha_salida.weekday()] for v in (pasado, cancelado)}
        restantes = [d for d in DIAS_VALIDOS if d not in dias_quitados]
        form = HorarioForm(data=self.datos_horario(dias_semana=",".join(restantes)), instance=self.horario)
        self.assertTrue(form.is_valid(), form.errors)


class EliminarYActivarHorarioTests(GestionRutasTestCase):
    def test_horario_sin_viajes_se_elimina(self):
        self.client.post(reverse("rutas:horario_eliminar", args=[self.horario.pk]))
        self.assertFalse(Horario.objects.filter(pk=self.horario.pk).exists())

    def test_horario_con_viajes_no_se_elimina(self):
        self.programar()
        url = reverse("rutas:horario_eliminar", args=[self.horario.pk])
        self.assertTrue(self.client.get(url).context["bloqueado"])
        self.client.post(url)
        self.assertTrue(Horario.objects.filter(pk=self.horario.pk).exists())

    def test_alterna_el_estado_del_horario(self):
        url = reverse("rutas:horario_activar", args=[self.horario.pk])
        respuesta = self.client.post(url)
        self.assertRedirects(respuesta, reverse("rutas:horarios", kwargs={"ruta_id": self.ruta.pk}))
        self.horario.refresh_from_db()
        self.assertFalse(self.horario.activo)


class PermisosAccionesPostTests(GestionRutasTestCase):
    def test_roles_sin_permiso_no_modifican_nada(self):
        urls = [
            reverse("rutas:activar", args=[self.ruta.pk]),
            reverse("rutas:eliminar", args=[self.ruta.pk]),
            reverse("rutas:horario_activar", args=[self.horario.pk]),
            reverse("rutas:horario_eliminar", args=[self.horario.pk]),
        ]
        for rol in ("cliente", "ventanillero", "conductor"):
            self.client.force_login(Usuario.objects.create_user(f"u_{rol}", rol=rol, terminal_asignado=self.la_paz))
            for url in urls:
                with self.subTest(rol=rol, url=url):
                    self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(Ruta.objects.get(pk=self.ruta.pk).activa)
        self.assertTrue(Horario.objects.get(pk=self.horario.pk).activo)
