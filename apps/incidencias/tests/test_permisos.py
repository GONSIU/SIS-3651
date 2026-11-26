from django.test import TestCase
from django.urls import reverse

from apps.incidencias.models import Incidencia
from apps.rutas.models import Terminal
from apps.usuarios.models import Usuario

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


class IncidenciasPermisosTests(ComprobarPermisosMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = crear_usuarios_por_rol(Terminal.objects.create(nombre="Bimodal", ciudad="La Paz"))
        cls.incidencia = Incidencia.objects.create(
            categoria="otro", titulo="X", descripcion="Y", reportado_por=cls.usuarios["admin"]
        )

    def test_pantallas_del_personal(self):
        self.comprobar_get(
            [
                reverse("incidencias:listado"),
                reverse("incidencias:nueva"),
                reverse("incidencias:detalle", args=[self.incidencia.pk]),
            ],
            {"supervisor", "admin"},
        )

    def test_pantallas_del_cliente(self):
        self.comprobar_get(
            [reverse("incidencias:mis_reclamos"), reverse("incidencias:nuevo_reclamo")], {"cliente"}
        )

    def test_cambiar_estado_solo_gestion(self):
        url = reverse("incidencias:cambiar_estado", args=[self.incidencia.pk])
        for rol, usuario in self.usuarios.items():
            with self.subTest(rol=rol):
                self.client.force_login(usuario)
                esperado = 302 if rol in {"supervisor", "admin"} else 403
                self.assertEqual(self.client.post(url, {"estado": "en_revision"}).status_code, esperado)
