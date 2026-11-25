from datetime import date, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.flota.models import Bus
from apps.personal.models import Empleado
from apps.rutas.models import DIAS_VALIDOS, Horario, Ruta, Terminal
from apps.usuarios.models import Usuario
from apps.viajes.models import Viaje

ROLES = ("cliente", "ventanillero", "supervisor", "admin", "conductor")


def crear_usuarios_por_rol(terminal) -> dict:
    return {
        rol: Usuario.objects.create_user(f"perm_{rol}", rol=rol, terminal_asignado=terminal)
        for rol in ROLES
    }


class ComprobarPermisosMixin:
    """Sin sesion -> 302 al login; rol no autorizado -> 403; rol autorizado -> 200."""

    def comprobar_get(self, urls: list[str], autorizados: set[str]) -> None:
        for url in urls:
            with self.subTest(url=url, rol="anonimo"):
                self.client.logout()
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta["Location"].startswith(reverse("usuarios:login")))
            for rol, usuario in self.usuarios.items():
                with self.subTest(url=url, rol=rol):
                    self.client.force_login(usuario)
                    esperado = 200 if rol in autorizados else 403
                    self.assertEqual(self.client.get(url).status_code, esperado)


class ViajesPermisosTests(ComprobarPermisosMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = crear_usuarios_por_rol(Terminal.objects.create(nombre="Bimodal", ciudad="La Paz"))

    def test_permisos(self):
        self.comprobar_get([reverse("viajes:listado"), reverse("viajes:nuevo")], {"supervisor", "admin"})

    def test_mis_viajes_solo_conductor(self):
        self.comprobar_get([reverse("viajes:mis_viajes")], {"conductor"})

    def test_hoja_ruta_conductor_asignado_supervisor_y_admin(self):
        terminal = self.usuarios["admin"].terminal_asignado
        ruta = Ruta.objects.create(origen=terminal, destino=Terminal.objects.create(nombre="Central", ciudad="Oruro"))
        horario = Horario.objects.create(ruta=ruta, hora_salida=time(8), dias_semana=",".join(DIAS_VALIDOS))
        bus = Bus.objects.create(placa="1234ABC", nombre_tipo="Cama", capacidad_pasajeros=10, capacidad_carga_kg=0)
        conductor = Empleado.objects.create(
            usuario=self.usuarios["conductor"], cargo="conductor", fecha_ingreso=date(2024, 1, 1)
        )
        viaje = Viaje.objects.create(
            ruta=ruta, horario=horario, bus=bus, conductor=conductor,
            fecha_salida=timezone.localdate() + timedelta(days=1),
        )
        self.comprobar_get([reverse("viajes:hoja_ruta", args=[viaje.pk])], {"conductor", "supervisor", "admin"})
