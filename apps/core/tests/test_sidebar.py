import re

from django.urls import reverse

from apps.ventas.tests.base import VentasTestCase


class MenuVentasTests(VentasTestCase):
    """Venta de Boletos es un submenu desplegable con nueva venta, reservas y reprogramaciones."""

    def setUp(self):
        self.client.force_login(self.vendedor)

    def menu(self, url: str) -> str:
        html = self.client.get(url).content.decode()
        bloque = re.search(r"<details[^>]*data-menu-ventas.*?</details>", html, re.S)
        self.assertIsNotNone(bloque, "No se encontro el submenu de ventas")
        return bloque.group(0)

    def test_contiene_las_tres_opciones(self):
        menu = self.menu(reverse("core:index"))
        for nombre in ("ventas:nueva_venta", "ventas:reservas_pendientes", "ventas:reprogramaciones"):
            with self.subTest(nombre=nombre):
                self.assertIn(f'href="{reverse(nombre)}"', menu)

    def test_abierto_y_resaltado_en_pantallas_de_ventas(self):
        for nombre in ("ventas:nueva_venta", "ventas:reservas_pendientes", "ventas:reprogramaciones"):
            with self.subTest(nombre=nombre):
                menu = self.menu(reverse(nombre))
                self.assertRegex(menu.split(">", 1)[0], r"\bopen\b")
                self.assertRegex(menu, rf'nav-link active[^>]*href="{re.escape(reverse(nombre))}"')

    def test_cerrado_fuera_de_ventas(self):
        menu = self.menu(reverse("encomiendas:listado"))
        self.assertNotRegex(menu.split(">", 1)[0], r"\bopen\b")
