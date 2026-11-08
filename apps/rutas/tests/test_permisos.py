from django.test import TestCase
from django.urls import reverse

from apps.rutas.models import Ruta, Terminal
from apps.usuarios.models import Usuario

ROLES = ("cliente", "ventanillero", "supervisor", "admin")


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


class RutasPermisosTests(ComprobarPermisosMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        origen = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        destino = Terminal.objects.create(nombre="Central", ciudad="Oruro")
        cls.ruta = Ruta.objects.create(origen=origen, destino=destino)
        cls.usuarios = crear_usuarios_por_rol(origen)

    def test_permisos(self):
        self.comprobar_get(
            [
                reverse("rutas:listado"),
                reverse("rutas:nuevo"),
                reverse("rutas:terminal_nuevo"),
                reverse("rutas:horarios", kwargs={"ruta_id": self.ruta.pk}),
                reverse("rutas:horario_nuevo", kwargs={"ruta_id": self.ruta.pk}),
            ],
            {"supervisor", "admin"},
        )
