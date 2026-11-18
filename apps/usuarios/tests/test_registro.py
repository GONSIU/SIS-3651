from django.test import TestCase
from django.urls import reverse

from apps.usuarios.forms import RegistroClienteForm
from apps.usuarios.models import Usuario

URL = reverse("usuarios:registro")


def datos(**cambios) -> dict:
    valores = {
        "username": "ana", "email": "ana@example.com", "first_name": "Ana", "last_name": "Perez",
        "telefono": "71234567", "ci": "1234567",
        "password1": "clave-Segura-913", "password2": "clave-Segura-913",
    }
    valores.update(cambios)
    return valores


class RegistroObligatoriosTests(TestCase):
    def test_nombre_apellido_y_ci_son_obligatorios(self):
        for campo in RegistroClienteForm.CAMPOS_OBLIGATORIOS:
            with self.subTest(campo=campo):
                form = RegistroClienteForm(data=datos(**{campo: ""}))
                self.assertIn(campo, form.errors)

    def test_ci_repetido_se_rechaza(self):
        Usuario.objects.create_user("otro", ci="1234567")
        self.assertIn("ci", RegistroClienteForm(data=datos()).errors)


class RegistroViewTests(TestCase):
    def test_crea_la_cuenta_inicia_sesion_y_va_a_mis_pasajes(self):
        respuesta = self.client.post(URL, datos())
        self.assertRedirects(respuesta, reverse("ventas:mis_pasajes"))
        usuario = Usuario.objects.get(username="ana")
        self.assertEqual(usuario.rol, "cliente")
        self.assertEqual(int(self.client.session["_auth_user_id"]), usuario.pk)

    def test_vuelve_al_next_seguro(self):
        destino = reverse("ventas:buscar_viajes")
        respuesta = self.client.post(f"{URL}?next={destino}", datos())
        self.assertRedirects(respuesta, destino)

    def test_next_en_el_post_tambien_sirve(self):
        destino = reverse("ventas:buscar_viajes")
        respuesta = self.client.post(URL, datos(next=destino))
        self.assertRedirects(respuesta, destino)

    def test_next_externo_se_ignora(self):
        respuesta = self.client.post(URL, datos(next="https://sitio-malicioso.example/"))
        self.assertRedirects(respuesta, reverse("ventas:mis_pasajes"))

    def test_formulario_conserva_el_next(self):
        respuesta = self.client.get(URL, {"next": "/ventas/viajes/"})
        self.assertContains(respuesta, 'name="next" value="/ventas/viajes/"')
