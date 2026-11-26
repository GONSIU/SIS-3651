from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.usuarios.models import Usuario


class PoblarDemoTests(TestCase):
    """Solo las protecciones: la ejecucion completa tarda minutos y se prueba a mano."""

    @override_settings(DEBUG=False)
    def test_no_corre_sin_debug(self):
        with self.assertRaisesMessage(CommandError, "DEBUG=True"):
            call_command("poblar_demo")

    @override_settings(DEBUG=True)
    def test_no_mezcla_con_datos_existentes(self):
        Usuario.objects.create_user("existente")
        with self.assertRaisesMessage(CommandError, "--limpiar"):
            call_command("poblar_demo")
        self.assertEqual(Usuario.objects.count(), 1)
