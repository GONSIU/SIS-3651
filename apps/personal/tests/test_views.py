from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.personal.forms import EmpleadoForm
from apps.personal.models import Empleado
from apps.rutas.models import Terminal
from apps.usuarios.models import Usuario


class PersonalTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.terminal = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        cls.supervisor = Usuario.objects.create_user(
            "sup", rol="supervisor", terminal_asignado=cls.terminal
        )
        cls.ventanillero = Usuario.objects.create_user(
            "vent", rol="ventanillero", terminal_asignado=cls.terminal
        )
        cls.admin = Usuario.objects.create_user("admin", rol="admin")
        cls.cliente = Usuario.objects.create_user("cli")


class PermisosTests(PersonalTestCase):
    URLS = ["personal:listado", "personal:nuevo", "personal:desempeno"]

    def test_anonimo_va_al_login(self):
        for nombre in self.URLS:
            with self.subTest(url=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertEqual(respuesta.status_code, 302)
                self.assertIn(reverse("usuarios:login"), respuesta["Location"])

    def test_acceso_por_rol(self):
        esperado = {self.cliente: 403, self.ventanillero: 403, self.supervisor: 200, self.admin: 200}
        for usuario, codigo in esperado.items():
            self.client.force_login(usuario)
            for nombre in self.URLS:
                with self.subTest(rol=usuario.rol, url=nombre):
                    self.assertEqual(self.client.get(reverse(nombre)).status_code, codigo)

    def test_enlace_del_sidebar_segun_rol(self):
        enlace = f'href="{reverse("personal:listado")}"'
        for usuario, visible in ((self.supervisor, True), (self.admin, True),
                                 (self.ventanillero, False), (self.cliente, False)):
            with self.subTest(rol=usuario.rol):
                self.client.force_login(usuario)
                respuesta = self.client.get(reverse("core:index"))
                if visible:
                    self.assertContains(respuesta, enlace)
                else:
                    self.assertNotContains(respuesta, enlace)


class EmpleadoFormTests(PersonalTestCase):
    def test_solo_ofrece_personal_activo_sin_ficha(self):
        con_ficha = Usuario.objects.create_user("karen", rol="ventanillero", terminal_asignado=self.terminal)
        Empleado.objects.create(usuario=con_ficha, cargo="Cajera", fecha_ingreso=timezone.localdate())
        Usuario.objects.create_user("baja", rol="ventanillero", is_active=False,
                                    terminal_asignado=self.terminal)

        ofrecidos = set(EmpleadoForm().fields["usuario"].queryset)
        self.assertEqual(ofrecidos, {self.supervisor, self.ventanillero, self.admin})

    def test_lista_al_dia_entre_formularios(self):
        # El queryset declarado en la clase se reevalua en cada formulario.
        EmpleadoForm()
        nuevo = Usuario.objects.create_user("nuevo", rol="admin")
        self.assertIn(nuevo, EmpleadoForm().fields["usuario"].queryset)

    def test_rechaza_cliente_aunque_se_envie_a_mano(self):
        form = EmpleadoForm(data={"usuario": self.cliente.pk, "cargo": "Cajero",
                                  "fecha_ingreso": timezone.localdate()})
        self.assertFalse(form.is_valid())
        self.assertIn("aun no tenga ficha", form.errors["usuario"][0])


class NuevoEmpleadoViewTests(PersonalTestCase):
    def setUp(self):
        self.client.force_login(self.supervisor)

    def test_preselecciona_usuario_de_la_url(self):
        respuesta = self.client.get(reverse("personal:nuevo"), {"usuario": self.ventanillero.pk})
        self.assertEqual(respuesta.context["form"].initial["usuario"], self.ventanillero.pk)

    def test_ignora_parametro_no_numerico(self):
        respuesta = self.client.get(reverse("personal:nuevo"), {"usuario": "abc"})
        self.assertNotIn("usuario", respuesta.context["form"].initial)

    def test_crea_ficha(self):
        respuesta = self.client.post(reverse("personal:nuevo"), {
            "usuario": self.ventanillero.pk, "cargo": "Cajero",
            "fecha_ingreso": timezone.localdate().isoformat(),
        })
        self.assertRedirects(respuesta, reverse("personal:listado"))
        self.assertEqual(self.ventanillero.empleado.cargo, "Cajero")

    def test_avisa_si_no_hay_candidatos(self):
        # El supervisor sigue activo (tiene la sesion): se le da ficha para excluirlo.
        Empleado.objects.create(usuario=self.supervisor, cargo="Jefe", fecha_ingreso=timezone.localdate())
        Usuario.objects.exclude(rol="cliente").exclude(pk=self.supervisor.pk).update(is_active=False)
        respuesta = self.client.get(reverse("personal:nuevo"))
        self.assertFalse(respuesta.context["hay_candidatos"])
        self.assertContains(respuesta, "No hay usuarios de personal sin ficha")

    def test_listado_cuenta_personal_sin_ficha(self):
        respuesta = self.client.get(reverse("personal:listado"))
        self.assertEqual(respuesta.context["sin_ficha"], 3)
