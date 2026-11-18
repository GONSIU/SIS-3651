from types import SimpleNamespace

from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.contrib.auth.models import AnonymousUser

from apps.core.middleware import LoginObligatorioMiddleware
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


class DashboardPermisosTests(ComprobarPermisosMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = crear_usuarios_por_rol(Terminal.objects.create(nombre="Bimodal", ciudad="La Paz"))

    def test_permisos(self):
        self.comprobar_get([reverse("core:index")], {"ventanillero", "supervisor", "admin"})


class LoginObligatorioMiddlewareTests(TestCase):
    """Rutas publicas por la pila completa y casos sueltos sobre el middleware."""

    def test_vistas_publicas_sin_sesion(self):
        for nombre in ("usuarios:login", "usuarios:registro"):
            with self.subTest(vista=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)

    def test_raiz_redirige_al_login_sin_next(self):
        self.assertRedirects(self.client.get("/"), reverse("usuarios:login"))

    def test_logout_sin_sesion_no_exige_login(self):
        self.assertRedirects(self.client.post(reverse("usuarios:logout")), reverse("usuarios:login"))

    def test_admin_de_django_usa_su_propio_login(self):
        respuesta = self.client.get("/admin/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta["Location"].startswith("/admin/login/"))

    def test_redirige_con_next(self):
        respuesta = self.client.get(reverse("viajes:listado") + "?page=2")
        self.assertEqual(
            respuesta["Location"], reverse("usuarios:login") + "?next=/viajes/%3Fpage%3D2"
        )

    def procesar(self, path: str, view_name: str, namespaces: list[str], usuario=None):
        request = RequestFactory().get(path)
        request.user = usuario or AnonymousUser()
        request.resolver_match = SimpleNamespace(view_name=view_name, namespaces=namespaces)
        middleware = LoginObligatorioMiddleware(lambda r: HttpResponse())
        return middleware.process_view(request, None, (), {})

    def test_vista_nueva_sin_mixin_queda_protegida(self):
        respuesta = self.procesar("/nueva/", "nueva_app:vista", ["nueva_app"])
        self.assertEqual(respuesta.status_code, 302)

    def test_estaticos_no_exigen_sesion(self):
        self.assertIsNone(self.procesar("/static/css/app.css", "", []))

    def test_media_exige_sesion(self):
        self.assertEqual(self.procesar("/media/x.pdf", "", []).status_code, 302)

    def test_usuario_con_sesion_pasa(self):
        usuario = Usuario.objects.create_user("ana")
        self.assertIsNone(self.procesar("/nueva/", "nueva_app:vista", ["nueva_app"], usuario))
