from datetime import date, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.encomiendas.models import Encomienda
from apps.flota.models import Bus
from apps.personal.models import Empleado
from apps.rutas.models import DIAS_VALIDOS, Horario, Ruta, Terminal
from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje
from apps.viajes.forms import ViajeForm
from apps.viajes.models import Viaje

TODOS_LOS_DIAS = ",".join(DIAS_VALIDOS)


class ConductorTestCase(TestCase):
    """Datos comunes: dos rutas con horario a la misma hora, un bus y dos conductores."""

    @classmethod
    def setUpTestData(cls):
        cls.la_paz = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        cls.oruro = Terminal.objects.create(nombre="Central", ciudad="Oruro")
        cls.ruta = Ruta.objects.create(origen=cls.la_paz, destino=cls.oruro)
        cls.otra_ruta = Ruta.objects.create(origen=cls.oruro, destino=cls.la_paz)
        cls.horario = Horario.objects.create(ruta=cls.ruta, hora_salida=time(8), dias_semana=TODOS_LOS_DIAS)
        cls.horario_misma_hora = Horario.objects.create(
            ruta=cls.otra_ruta, hora_salida=time(8), dias_semana=TODOS_LOS_DIAS
        )
        cls.bus = Bus.objects.create(
            placa="1234ABC", nombre_tipo="Semicama", capacidad_pasajeros=12, capacidad_carga_kg=500
        )
        cls.otro_bus = Bus.objects.create(
            placa="5678DEF", nombre_tipo="Cama", capacidad_pasajeros=12, capacidad_carga_kg=500
        )
        cls.conductor = cls.crear_empleado("chofer1", "conductor")
        cls.otro_conductor = cls.crear_empleado("chofer2", "conductor")
        cls.hoy = timezone.localdate()
        cls.manana = cls.hoy + timedelta(days=1)

    @staticmethod
    def crear_empleado(username: str, rol: str, activo: bool = True) -> Empleado:
        usuario = Usuario.objects.create_user(username, rol=rol, is_active=activo, first_name=username.title())
        return Empleado.objects.create(usuario=usuario, cargo=Empleado.cargos_para_rol(rol)[0], fecha_ingreso=date(2024, 1, 1))

    def viaje(self, **kwargs) -> Viaje:
        datos = {
            "ruta": self.ruta,
            "horario": self.horario,
            "bus": self.bus,
            "conductor": self.conductor,
            "fecha_salida": self.manana,
        }
        datos.update(kwargs)
        return Viaje(**datos)

    def errores(self, viaje: Viaje) -> dict:
        with self.assertRaises(ValidationError) as ctx:
            viaje.full_clean()
        return ctx.exception.message_dict


class ViajeConductorModelTests(ConductorTestCase):
    def test_viaje_con_conductor_valido(self):
        self.viaje().full_clean()

    def test_conductor_es_opcional(self):
        self.viaje(conductor=None).full_clean()

    def test_empleado_sin_rol_conductor_se_rechaza(self):
        for rol in ("ventanillero", "supervisor", "admin"):
            with self.subTest(rol=rol):
                empleado = self.crear_empleado(f"emp_{rol}", rol)
                self.assertIn("conductor", self.errores(self.viaje(conductor=empleado)))

    def test_conductor_inactivo_se_rechaza(self):
        inactivo = self.crear_empleado("chofer_baja", "conductor", activo=False)
        self.assertIn("conductor", self.errores(self.viaje(conductor=inactivo)))

    def test_conductor_no_puede_tener_dos_viajes_a_la_misma_hora(self):
        self.viaje().save()
        viaje = self.viaje(ruta=self.otra_ruta, horario=self.horario_misma_hora, bus=self.otro_bus)
        self.assertIn("conductor", self.errores(viaje))

    def test_viaje_cancelado_libera_al_conductor(self):
        self.viaje(estado="cancelado").save()
        self.viaje(ruta=self.otra_ruta, horario=self.horario_misma_hora, bus=self.otro_bus).full_clean()

    def test_otro_conductor_a_la_misma_hora_no_es_conflicto(self):
        self.viaje().save()
        self.viaje(
            ruta=self.otra_ruta, horario=self.horario_misma_hora, bus=self.otro_bus, conductor=self.otro_conductor
        ).full_clean()

    def test_editar_viaje_no_choca_consigo_mismo(self):
        viaje = self.viaje()
        viaje.save()
        viaje.full_clean()

    def test_conductor_que_cambia_de_rol_no_impide_editar_el_viaje(self):
        viaje = self.viaje()
        viaje.save()
        Usuario.objects.filter(pk=self.conductor.usuario_id).update(rol="ventanillero")
        viaje = Viaje.objects.get(pk=viaje.pk)
        viaje.full_clean()

    def test_cambiar_a_un_conductor_invalido_falla(self):
        viaje = self.viaje()
        viaje.save()
        viaje.conductor = self.crear_empleado("emp_venta", "ventanillero")
        self.assertIn("conductor", self.errores(viaje))


class ViajeFormConductorTests(ConductorTestCase):
    def test_solo_lista_conductores_activos(self):
        self.crear_empleado("chofer_baja", "conductor", activo=False)
        self.crear_empleado("emp_venta", "ventanillero")
        opciones = set(ViajeForm().fields["conductor"].queryset)
        self.assertEqual(opciones, {self.conductor, self.otro_conductor})

    def test_rechaza_un_empleado_fuera_de_la_lista(self):
        empleado = self.crear_empleado("emp_venta", "ventanillero")
        form = ViajeForm(
            data={
                "horario": self.horario.pk,
                "bus": self.bus.pk,
                "conductor": empleado.pk,
                "fecha_salida": self.manana.isoformat(),
                "estado": "programado",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("conductor", form.errors)


class MisViajesViewTests(ConductorTestCase):
    url = reverse("viajes:mis_viajes")

    def setUp(self):
        self.proximo = self.viaje()
        self.proximo.save()
        # objects.create no ejecuta clean(): permite un viaje con fecha pasada.
        self.pasado = Viaje.objects.create(
            ruta=self.ruta, horario=self.horario, bus=self.bus, conductor=self.conductor,
            fecha_salida=self.hoy - timedelta(days=3), estado="completado",
        )
        self.ajeno = self.viaje(
            ruta=self.otra_ruta, horario=self.horario_misma_hora, bus=self.otro_bus, conductor=self.otro_conductor
        )
        self.ajeno.save()
        self.client.force_login(self.conductor.usuario)

    def test_muestra_solo_los_proximos_viajes_propios(self):
        viajes = list(self.client.get(self.url).context["viajes"])
        self.assertEqual(viajes, [self.proximo])

    def test_historial_muestra_los_viajes_pasados(self):
        respuesta = self.client.get(self.url, {"historial": "1"})
        self.assertEqual(list(respuesta.context["viajes"]), [self.pasado])
        self.assertTrue(respuesta.context["es_historial"])

    def test_conductor_sin_viajes_ve_la_lista_vacia(self):
        self.client.force_login(self.crear_empleado("chofer3", "conductor").usuario)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(list(respuesta.context["viajes"]), [])


class HojaRutaViewTests(ConductorTestCase):
    def setUp(self):
        self.bus.crear_asientos()
        self.viaje_propio = self.viaje()
        self.viaje_propio.save()
        self.viaje_propio.crear_asientos_desde_bus()
        self.url = reverse("viajes:hoja_ruta", args=[self.viaje_propio.pk])

    def vender(self, numero: str, estado: str, nombre: str) -> Pasaje:
        asiento_viaje = self.viaje_propio.asientos_viaje.get(asiento__numero=numero)
        return Pasaje.objects.create(
            viaje=self.viaje_propio, asiento_viaje=asiento_viaje, cliente_nombre=nombre,
            canal="ventanilla", precio=Decimal("50"), estado=estado,
        )

    def test_conductor_ve_su_hoja_de_ruta(self):
        self.client.force_login(self.conductor.usuario)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_viaje_de_otro_conductor_da_404(self):
        self.client.force_login(self.otro_conductor.usuario)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_supervisor_y_admin_ven_cualquier_hoja_de_ruta(self):
        for rol in ("supervisor", "admin"):
            with self.subTest(rol=rol):
                self.client.force_login(Usuario.objects.create_user(f"u_{rol}", rol=rol, terminal_asignado=self.la_paz))
                self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_pasajeros_ordenados_por_numero_y_sin_cancelados(self):
        self.vender("10", "pagado", "Diez")
        self.vender("2", "reservado", "Dos")
        self.vender("1", "cancelado", "Uno")
        self.client.force_login(self.conductor.usuario)
        pasajes = self.client.get(self.url).context["pasajes"]
        self.assertEqual([p.cliente_nombre for p in pasajes], ["Dos", "Diez"])

    def test_encomiendas_a_bordo_y_peso_total(self):
        registrador = Usuario.objects.create_user("venta", rol="ventanillero", terminal_asignado=self.la_paz)
        datos = {
            "viaje": self.viaje_propio, "remitente_nombre": "Ana", "remitente_ci": "1234567",
            "destinatario_nombre": "Luis", "destinatario_ci": "7654321",
            "descripcion_contenido": "Ropa", "registrado_por": registrador,
        }
        Encomienda.objects.create(peso_kg=Decimal("5"), **datos)
        Encomienda.objects.create(peso_kg=Decimal("2.5"), **datos)
        Encomienda.objects.create(peso_kg=Decimal("9"), estado="extraviado", **datos)
        self.client.force_login(self.conductor.usuario)
        contexto = self.client.get(self.url).context
        self.assertEqual(len(contexto["encomiendas"]), 2)
        self.assertEqual(contexto["peso_total_kg"], Decimal("7.5"))


class LoginRedireccionPorRolTests(ConductorTestCase):
    url = reverse("usuarios:login")

    def login(self, usuario: Usuario, **extra):
        usuario.set_password("clave-segura-123")
        usuario.save()
        datos = {"username": usuario.username, "password": "clave-segura-123", **extra}
        return self.client.post(self.url, datos)

    def test_conductor_va_a_mis_viajes(self):
        self.assertRedirects(self.login(self.conductor.usuario), reverse("viajes:mis_viajes"))

    def test_otros_roles_van_al_dashboard(self):
        usuario = Usuario.objects.create_user("venta", rol="ventanillero", terminal_asignado=self.la_paz)
        respuesta = self.login(usuario)
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta["Location"], reverse("core:index"))

    def test_next_tiene_prioridad(self):
        viaje = self.viaje()
        viaje.save()
        destino = reverse("viajes:hoja_ruta", args=[viaje.pk])
        self.assertRedirects(self.login(self.conductor.usuario, next=destino), destino)

    def test_next_externo_se_ignora(self):
        respuesta = self.login(self.conductor.usuario, next="https://sitio-malicioso.example/")
        self.assertEqual(respuesta["Location"], reverse("viajes:mis_viajes"))
