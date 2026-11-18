from decimal import Decimal

from django.urls import reverse

from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje
from .base import VentasTestCase

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


class VentasPermisosTests(ComprobarPermisosMixin, VentasTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.usuarios = crear_usuarios_por_rol(cls.ruta.origen)
        cls.pasaje = Pasaje.objects.create(
            viaje=cls.viaje, asiento_viaje=cls.asiento, cliente_nombre="Ana Perez",
            canal="ventanilla", precio=Decimal("50"),
        )

    def test_permisos(self):
        self.comprobar_get(
            [reverse("ventas:nueva_venta"), reverse("ventas:boleto", kwargs={"pk": self.pasaje.pk})],
            {"ventanillero", "supervisor", "admin"},
        )

    def test_post_de_venta_sin_rol_no_vende(self):
        self.client.force_login(self.usuarios["cliente"])
        respuesta = self.client.post(reverse("ventas:nueva_venta"), {"viaje_id": self.viaje.pk})
        self.assertEqual(respuesta.status_code, 403)
