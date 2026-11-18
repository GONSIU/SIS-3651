from django.urls import reverse

from apps.usuarios.models import Usuario
from .base import EncomiendasTestCase

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


class EncomiendasPermisosTests(ComprobarPermisosMixin, EncomiendasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.usuarios = crear_usuarios_por_rol(cls.ruta.origen)

    def setUp(self):
        self.encomienda = self.crear_encomienda()

    def test_permisos(self):
        self.comprobar_get(
            [
                reverse("encomiendas:listado"),
                reverse("encomiendas:nueva"),
                reverse("encomiendas:guia", kwargs={"pk": self.encomienda.pk}),
            ],
            {"ventanillero", "supervisor", "admin"},
        )

    def test_permisos_cambiar_estado(self):
        # Solo acepta POST: un rol autorizado vuelve al listado.
        url = reverse("encomiendas:cambiar_estado", kwargs={"pk": self.encomienda.pk})
        datos = {"estado": "en_transito"}
        self.client.logout()
        respuesta = self.client.post(url, datos)
        self.assertTrue(respuesta["Location"].startswith(reverse("usuarios:login")))
        for rol, usuario in self.usuarios.items():
            with self.subTest(rol=rol):
                self.client.force_login(usuario)
                respuesta = self.client.post(url, datos)
                if rol in {"ventanillero", "supervisor", "admin"}:
                    self.assertRedirects(respuesta, reverse("encomiendas:listado"))
                else:
                    self.assertEqual(respuesta.status_code, 403)
