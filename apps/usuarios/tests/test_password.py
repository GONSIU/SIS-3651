from django.test import TestCase
from django.urls import reverse

from apps.rutas.models import Terminal
from apps.usuarios.models import Usuario

TEMPORAL = "temporal-Inicial-482"
NUEVA = "propia-Segura-771"
URL = reverse("usuarios:cambiar_password")


class PasswordTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.terminal = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        cls.admin = Usuario.objects.create_user("admin1", password=TEMPORAL, rol="admin")

    def crear(self, username: str, **kwargs) -> Usuario:
        datos = {"password": TEMPORAL, "rol": "ventanillero", "terminal_asignado": self.terminal}
        return Usuario.objects.create_user(username, **{**datos, **kwargs})

    def cambiar(self, actual: str = TEMPORAL, nueva: str = NUEVA, repetida: str | None = None):
        return self.client.post(URL, {
            "old_password": actual, "new_password1": nueva, "new_password2": repetida or nueva,
        })


class MarcaTemporalTests(PasswordTestCase):
    def test_alta_por_el_admin_queda_temporal(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("usuarios:nuevo"), {
            "username": "sup1", "first_name": "Juan", "last_name": "Perez",
            "email": "juan@example.com", "ci": "1234567", "telefono": "71234567",
            "rol": "supervisor", "terminal_asignado": self.terminal.pk,
            "password_temporal": TEMPORAL,
        })
        self.assertTrue(Usuario.objects.get(username="sup1").debe_cambiar_password)

    def test_cliente_registrado_no_queda_temporal(self):
        self.client.post(reverse("usuarios:registro"), {
            "username": "cli1", "first_name": "Ana", "last_name": "Rojas",
            "email": "ana@example.com", "ci": "7654321", "telefono": "71111111",
            "password1": NUEVA, "password2": NUEVA,
        })
        self.assertFalse(Usuario.objects.get(username="cli1").debe_cambiar_password)

    def test_restablecer_a_otro_queda_temporal(self):
        vent = self.crear("vent1")
        self.client.force_login(self.admin)
        self.client.post(reverse("usuarios:restablecer_password", args=[vent.pk]), {
            "new_password1": NUEVA, "new_password2": NUEVA,
        })
        vent.refresh_from_db()
        self.assertTrue(vent.debe_cambiar_password)
        self.assertTrue(vent.check_password(NUEVA))

    def test_restablecer_la_propia_no_queda_temporal(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("usuarios:restablecer_password", args=[self.admin.pk]), {
            "new_password1": NUEVA, "new_password2": NUEVA,
        })
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.debe_cambiar_password)
        # update_session_auth_hash: la sesion del admin sigue abierta.
        self.assertEqual(self.client.get(reverse("usuarios:listado")).status_code, 200)


class CambioObligatorioTests(PasswordTestCase):
    def setUp(self):
        self.usuario = self.crear("vent1", debe_cambiar_password=True)
        self.client.force_login(self.usuario)

    def test_cualquier_pagina_redirige_a_cambiar(self):
        for url in (reverse("core:index"), reverse("viajes:listado"), reverse("core:root")):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), URL, fetch_redirect_response=False)

    def test_login_lleva_a_cambiar(self):
        self.client.logout()
        respuesta = self.client.post(
            reverse("usuarios:login"), {"username": "vent1", "password": TEMPORAL}, follow=True
        )
        self.assertEqual(respuesta.redirect_chain[-1][0], URL)
        self.assertContains(respuesta, "Tu contrasena es temporal")

    def test_puede_ver_el_formulario_y_salir(self):
        respuesta = self.client.get(URL)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["obligatorio"])
        self.assertNotContains(respuesta, f'href="{reverse("core:index")}">Cancelar')
        self.client.post(reverse("usuarios:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_estaticos_no_se_redirigen(self):
        respuesta = self.client.get("/static/css/styles.css")
        self.assertNotEqual(respuesta.status_code, 302)

    def test_cambio_correcto_quita_la_marca_y_mantiene_la_sesion(self):
        respuesta = self.cambiar()
        self.assertRedirects(respuesta, reverse("core:index"))
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.debe_cambiar_password)
        self.assertTrue(self.usuario.check_password(NUEVA))
        self.assertEqual(self.client.get(reverse("core:index")).status_code, 200)

    def test_actual_incorrecta_no_cambia_nada(self):
        respuesta = self.cambiar(actual="otra-cosa-123")
        self.assertIn("old_password", respuesta.context["form"].errors)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.debe_cambiar_password)
        self.assertTrue(self.usuario.check_password(TEMPORAL))

    def test_rechaza_nuevas_distintas_o_debiles(self):
        for nueva, repetida in ((NUEVA, NUEVA + "x"), ("123", "123")):
            with self.subTest(nueva=nueva):
                respuesta = self.cambiar(nueva=nueva, repetida=repetida)
                self.assertIn("new_password2", respuesta.context["form"].errors)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.debe_cambiar_password)


class CambioVoluntarioTests(PasswordTestCase):
    def test_anonimo_va_al_login(self):
        respuesta = self.client.get(URL)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("usuarios:login"), respuesta["Location"])

    def test_cada_rol_entra_con_su_layout(self):
        casos = {
            "cliente": "base_publico.html",
            "conductor": "base_dashboard.html",
            "ventanillero": "base_dashboard.html",
        }
        for rol, layout in casos.items():
            with self.subTest(rol=rol):
                self.client.force_login(self.crear(f"u_{rol}", rol=rol))
                respuesta = self.client.get(URL)
                self.assertEqual(respuesta.status_code, 200)
                self.assertTemplateUsed(respuesta, layout)
                self.assertFalse(respuesta.context["obligatorio"])
                self.assertContains(respuesta, f'href="{respuesta.context["url_volver"]}">Cancelar')

    def test_vuelve_al_inicio_del_rol(self):
        self.client.force_login(self.crear("cli1", rol="cliente", terminal_asignado=None))
        self.assertRedirects(self.cambiar(), reverse("ventas:mis_pasajes"))

    def test_enlace_en_los_menus(self):
        enlace = f'href="{URL}"'
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("core:index")), enlace)
        self.client.force_login(self.crear("cli1", rol="cliente", terminal_asignado=None))
        self.assertContains(self.client.get(reverse("core:salidas")), enlace)
