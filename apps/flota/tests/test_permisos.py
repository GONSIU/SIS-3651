from django.test import TestCase
from django.urls import reverse

from apps.rutas.models import Terminal
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


class FlotaPermisosTests(ComprobarPermisosMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = crear_usuarios_por_rol(Terminal.objects.create(nombre="Bimodal", ciudad="La Paz"))

    def test_permisos(self):
        self.comprobar_get([reverse("flota:listado"), reverse("flota:nuevo")], {"supervisor", "admin"})
