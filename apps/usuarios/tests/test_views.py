from django.test import TestCase
from django.urls import reverse

from apps.rutas.models import Terminal
from apps.usuarios.forms import UsuarioEditForm
from apps.usuarios.models import Usuario

PASSWORD = "clave-Segura-913"


class GestionUsuariosTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.terminal = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        cls.admin = Usuario.objects.create_user("admin1", password=PASSWORD, rol="admin")
        cls.ventanillero = Usuario.objects.create_user(
            "vent1", password=PASSWORD, rol="ventanillero", terminal_asignado=cls.terminal
        )

    def setUp(self):
        self.client.force_login(self.admin)


class PermisosTests(GestionUsuariosTestCase):
    URLS = [
        ("usuarios:listado", {}),
        ("usuarios:nuevo", {}),
        ("usuarios:editar", {"pk": 1}),
    ]

    def test_anonimo_va_al_login(self):
        self.client.logout()
        for nombre, kwargs in self.URLS:
            with self.subTest(url=nombre):
                respuesta = self.client.get(reverse(nombre, kwargs=kwargs))
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn(reverse("usuarios:login"), respuesta["Location"])

    def test_otro_rol_recibe_403(self):
        self.client.force_login(self.ventanillero)
        for nombre, kwargs in self.URLS:
            with self.subTest(url=nombre):
                kwargs = {"pk": self.admin.pk} if kwargs else {}
                self.assertEqual(self.client.get(reverse(nombre, kwargs=kwargs)).status_code, 403)

    def test_sidebar_solo_muestra_usuarios_al_admin(self):
        enlace = f'href="{reverse("usuarios:listado")}"'
        self.assertContains(self.client.get(reverse("core:index")), enlace)
        self.client.force_login(self.ventanillero)
        self.assertNotContains(self.client.get(reverse("core:index")), enlace)


class ListaUsuariosTests(GestionUsuariosTestCase):
    def listar(self, **params):
        return list(self.client.get(reverse("usuarios:listado"), params).context["usuarios"])

    def test_filtros(self):
        inactivo = Usuario.objects.create_user("vent2", rol="ventanillero", is_active=False,
                                               terminal_asignado=self.terminal)
        self.assertEqual(len(self.listar()), 3)
        self.assertEqual(self.listar(rol="admin"), [self.admin])
        self.assertEqual(self.listar(rol="ventanillero", activo="0"), [inactivo])
        self.assertEqual(self.listar(activo="1"), [self.admin, self.ventanillero])

    def test_filtro_invalido_se_ignora(self):
        self.assertEqual(len(self.listar(rol="hacker", activo="x")), 2)


class NuevoUsuarioTests(GestionUsuariosTestCase):
    def crear(self, **kwargs):
        datos = {
            "username": "sup1",
            "first_name": "Juan",
            "last_name": "Perez",
            "email": "juan@example.com",
            "ci": "1234567",
            "telefono": "71234567",
            "rol": "supervisor",
            "terminal_asignado": self.terminal.pk,
            "password_temporal": PASSWORD,
            **kwargs,
        }
        return self.client.post(reverse("usuarios:nuevo"), datos)

    def test_crea_con_password_hasheada(self):
        respuesta = self.crear()
        self.assertRedirects(respuesta, reverse("usuarios:listado"))
        usuario = Usuario.objects.get(username="sup1")
        self.assertEqual(usuario.rol, "supervisor")
        self.assertNotEqual(usuario.password, PASSWORD)
        self.assertTrue(usuario.check_password(PASSWORD))

    def test_no_ofrece_rol_cliente(self):
        respuesta = self.crear(rol="cliente", terminal_asignado="")
        self.assertIn("rol", respuesta.context["form"].errors)
        self.assertFalse(Usuario.objects.filter(username="sup1").exists())

    def test_rol_de_ventanilla_exige_terminal(self):
        respuesta = self.crear(terminal_asignado="")
        self.assertIn("terminal_asignado", respuesta.context["form"].errors)

    def test_rechaza_password_debil(self):
        for password in ("123", "password", "juan@example.com"):
            with self.subTest(password=password):
                respuesta = self.crear(password_temporal=password)
                self.assertIn("password_temporal", respuesta.context["form"].errors)
        self.assertFalse(Usuario.objects.filter(username="sup1").exists())

    def test_rechaza_ci_y_username_duplicados(self):
        Usuario.objects.create(username="otro", ci="1234567")
        respuesta = self.crear(username="admin1")
        errores = respuesta.context["form"].errors
        self.assertIn("username", errores)
        self.assertIn("ci", errores)


class EditarUsuarioTests(GestionUsuariosTestCase):
    def editar(self, usuario, **kwargs):
        datos = {"rol": usuario.rol, "terminal_asignado": usuario.terminal_asignado_id or "",
                 "is_active": "on", **kwargs}
        if datos["is_active"] is False:
            del datos["is_active"]
        return self.client.post(reverse("usuarios:editar", kwargs={"pk": usuario.pk}), datos)

    def test_cambia_rol_y_desactiva(self):
        respuesta = self.editar(self.ventanillero, rol="supervisor", is_active=False)
        self.assertRedirects(respuesta, reverse("usuarios:listado"))
        self.ventanillero.refresh_from_db()
        self.assertEqual(self.ventanillero.rol, "supervisor")
        self.assertFalse(self.ventanillero.is_active)

    def test_rol_de_ventanilla_exige_terminal(self):
        respuesta = self.editar(self.ventanillero, terminal_asignado="")
        self.assertIn("terminal_asignado", respuesta.context["form"].errors)

    def test_admin_no_se_degrada_ni_desactiva_a_si_mismo(self):
        Usuario.objects.create_user("admin2", rol="admin")  # no es el ultimo admin
        for cambio, campo in (({"rol": "supervisor", "terminal_asignado": self.terminal.pk}, "rol"),
                              ({"is_active": False}, "is_active")):
            with self.subTest(campo=campo):
                respuesta = self.editar(self.admin, **cambio)
                self.assertIn(campo, respuesta.context["form"].errors)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.rol, "admin")
        self.assertTrue(self.admin.is_active)

    def test_protege_al_ultimo_admin_activo(self):
        # Por la vista solo se llega aqui editandose a si mismo (otro admin activo ya
        # seria un segundo admin), asi que la regla se prueba en el formulario.
        editor = Usuario.objects.create_user("soporte", rol="supervisor",
                                             terminal_asignado=self.terminal)
        casos = [({"rol": "cliente", "is_active": True}, "rol"),
                 ({"rol": "admin", "is_active": False}, "is_active")]
        for datos, campo in casos:
            with self.subTest(campo=campo):
                form = UsuarioEditForm(data=datos, instance=self.admin, editor=editor)
                self.assertFalse(form.is_valid())
                self.assertIn("unico administrador", form.errors[campo][0])

    def test_otro_admin_puede_degradar_si_quedan_admins(self):
        otro = Usuario.objects.create_user("admin2", rol="admin")
        respuesta = self.editar(otro, rol="cliente")
        self.assertRedirects(respuesta, reverse("usuarios:listado"))
        otro.refresh_from_db()
        self.assertEqual(otro.rol, "cliente")
