import importlib

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.rutas.models import Terminal
from apps.usuarios.forms import RegistroClienteForm
from apps.usuarios.models import Usuario


class UsuarioTests(TestCase):
    def usuario(self, **kwargs) -> Usuario:
        return Usuario(**{"username": "ana", "password": "x", **kwargs})

    def test_normaliza_campos(self):
        usuario = self.usuario(
            first_name=" Ana   Maria ",
            last_name="Perez  Rojas",
            ci="123 4567-1b",
            telefono="+591 712-34567",
        )
        usuario.full_clean()
        self.assertEqual(usuario.first_name, "Ana Maria")
        self.assertEqual(usuario.last_name, "Perez Rojas")
        self.assertEqual(usuario.ci, "1234567-1B")
        self.assertEqual(usuario.telefono, "+59171234567")

    def test_campos_opcionales_vacios(self):
        usuario = self.usuario(first_name="", last_name="", ci="", telefono="")
        usuario.full_clean()
        self.assertIsNone(usuario.ci)

    def test_varios_usuarios_sin_ci(self):
        Usuario.objects.create(username="uno")
        self.usuario(ci="").full_clean()

    def test_rechaza_datos_invalidos(self):
        casos = [
            ("first_name", "as12"),
            ("last_name", "123"),
            ("first_name", "a" * 51),
            ("ci", "3ury237udbsn"),
            ("telefono", "abc"),
        ]
        for campo, valor in casos:
            with self.subTest(campo=campo, valor=valor):
                with self.assertRaises(ValidationError) as error:
                    self.usuario(**{campo: valor}).full_clean()
                self.assertIn(campo, error.exception.message_dict)

    def test_rol_de_ventanilla_exige_terminal(self):
        for rol in Usuario.ROLES_CON_TERMINAL:
            with self.subTest(rol=rol), self.assertRaises(ValidationError) as error:
                self.usuario(rol=rol).full_clean()
            self.assertIn("terminal_asignado", error.exception.message_dict)

    def test_rol_de_ventanilla_con_terminal_es_valido(self):
        terminal = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        for rol in Usuario.ROLES_CON_TERMINAL:
            with self.subTest(rol=rol):
                self.usuario(rol=rol, terminal_asignado=terminal).full_clean()

    def test_otros_roles_no_exigen_terminal(self):
        for rol in ("cliente", "admin"):
            with self.subTest(rol=rol):
                self.usuario(rol=rol).full_clean()


class RegistroClienteFormTests(TestCase):
    def datos(self, **kwargs) -> dict:
        return {
            "username": "ana",
            "email": "ana@example.com",
            "first_name": "Ana",
            "last_name": "Perez",
            "telefono": "7123-4567",
            "ci": "1234567",
            "password1": "clave-Segura-913",
            "password2": "clave-Segura-913",
            **kwargs,
        }

    def test_registro_valido_guarda_normalizado(self):
        form = RegistroClienteForm(data=self.datos())
        self.assertTrue(form.is_valid(), form.errors)
        usuario = form.save()
        self.assertEqual(usuario.telefono, "71234567")
        self.assertEqual(usuario.rol, "cliente")

    def test_registro_rechaza_nombre_invalido(self):
        form = RegistroClienteForm(data=self.datos(first_name="as12"))
        self.assertFalse(form.is_valid())
        self.assertIn("first_name", form.errors)


class UsuarioManagerTests(TestCase):
    def test_create_superuser_asigna_rol_admin(self):
        usuario = Usuario.objects.create_superuser("root", "root@example.com", "clave-Segura-913")
        self.assertEqual(usuario.rol, "admin")
        self.assertTrue(usuario.is_superuser)

    def test_create_superuser_rechaza_otro_rol(self):
        with self.assertRaises(ValueError):
            Usuario.objects.create_superuser("root", password="x", rol="cliente")

    def test_create_user_mantiene_rol_por_defecto(self):
        self.assertEqual(Usuario.objects.create_user("ana").rol, "cliente")


class SuperusuariosAAdminMigrationTests(TestCase):
    """Prueba la funcion de la migracion 0005 con el registro de apps actual."""

    def test_pasa_superusuarios_a_admin(self):
        from django.apps import apps as registro

        migracion = importlib.import_module("apps.usuarios.migrations.0005_superusuarios_a_admin")
        superusuario = Usuario.objects.create(username="root", is_superuser=True, rol="cliente")
        cliente = Usuario.objects.create(username="ana", rol="cliente")

        migracion.superusuarios_a_admin(registro, None)

        superusuario.refresh_from_db()
        cliente.refresh_from_db()
        self.assertEqual(superusuario.rol, "admin")
        self.assertEqual(cliente.rol, "cliente")


class EsUltimoAdminActivoTests(TestCase):
    def test_casos(self):
        admin = Usuario.objects.create(username="admin1", rol="admin")
        self.assertTrue(admin.es_ultimo_admin_activo())

        Usuario.objects.create(username="admin2", rol="admin", is_active=False)
        self.assertTrue(admin.es_ultimo_admin_activo(), "un admin inactivo no cuenta")

        Usuario.objects.create(username="admin3", rol="admin")
        self.assertFalse(admin.es_ultimo_admin_activo())

        cliente = Usuario.objects.create(username="ana")
        self.assertFalse(cliente.es_ultimo_admin_activo())
