from datetime import time
from decimal import Decimal
from pathlib import Path

from django.conf import settings

from django.test import TestCase
from django.urls import reverse

from apps.core.tests.test_permisos import crear_usuarios_por_rol
from apps.core.views import IMAGENES_CIUDADES, OrigenSalidas, salidas_por_origen
from apps.rutas.models import Horario, Ruta, Terminal

PAGINAS_PUBLICAS = ("core:root", "core:salidas", "core:nosotros")


class PaginasPublicasTests(TestCase):
    """Landing, Salidas y Sobre nosotros: publicas y con la misma barra superior."""

    @classmethod
    def setUpTestData(cls):
        cls.usuarios = crear_usuarios_por_rol(Terminal.objects.create(nombre="Bimodal", ciudad="La Paz"))

    def test_sin_sesion_responden_y_muestran_iniciar_sesion(self):
        for nombre in PAGINAS_PUBLICAS:
            with self.subTest(vista=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, reverse("usuarios:login"))
                self.assertContains(respuesta, reverse("usuarios:registro"))

    def test_navbar_enlaza_a_vistas_propias_sin_encomiendas_ni_compra(self):
        respuesta = self.client.get(reverse("core:nosotros"))
        for nombre in ("core:salidas", "core:nosotros"):
            with self.subTest(enlace=nombre):
                self.assertContains(respuesta, f'href="{reverse(nombre)}"')
        self.assertNotContains(respuesta, "Encomiendas")
        self.assertNotContains(respuesta, 'href="/#')
        self.assertNotContains(respuesta, reverse("ventas:buscar_viajes"))

    def test_logo_en_la_navbar_y_en_el_login(self):
        for nombre in PAGINAS_PUBLICAS + ("ventas:buscar_viajes", "usuarios:login"):
            with self.subTest(vista=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertContains(respuesta, "img/logo-trans-naser.png")
                self.assertNotContains(respuesta, "googleusercontent.com")

    def test_marca_la_pagina_actual(self):
        respuesta = self.client.get(reverse("core:salidas"))
        self.assertContains(respuesta, 'aria-current="page"', count=1)

    def test_con_sesion_muestra_nombre_y_panel_segun_rol(self):
        paneles = {
            "cliente": "ventas:mis_pasajes",
            "conductor": "viajes:mis_viajes",
            "ventanillero": "core:index",
            "supervisor": "core:index",
            "admin": "core:index",
        }
        for rol, panel in paneles.items():
            with self.subTest(rol=rol):
                self.client.force_login(self.usuarios[rol])
                respuesta = self.client.get(reverse("core:root"))
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, f"perm_{rol}")
                self.assertContains(respuesta, f'href="{reverse(panel)}"')
                self.assertContains(respuesta, reverse("usuarios:logout"))
                self.assertNotContains(respuesta, "Iniciar sesión")

    def test_no_incluye_contacto_por_whatsapp(self):
        for nombre in PAGINAS_PUBLICAS:
            with self.subTest(vista=nombre):
                self.assertNotContains(self.client.get(reverse(nombre)), "WhatsApp")


class LandingViewTests(TestCase):
    def test_solo_hero_con_boton_de_compra(self):
        respuesta = self.client.get(reverse("core:root"))
        self.assertTemplateUsed(respuesta, "core/landing.html")
        self.assertContains(respuesta, "img/hero-flota.jpg")
        self.assertContains(respuesta, "Compra tu pasaje en línea")
        self.assertNotIn("horarios", respuesta.context)


class SalidasViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        lp_central = Terminal.objects.create(nombre="Bimodal", ciudad="LA PAZ")
        lp_norte = Terminal.objects.create(nombre="Norte", ciudad="LA PAZ")
        oruro = Terminal.objects.create(nombre="Central", ciudad="ORURO")
        potosi = Terminal.objects.create(nombre="Nueva", ciudad="Potosi")
        sucre = Terminal.objects.create(nombre="Sucre", ciudad="Chuquisaca")
        uyuni = Terminal.objects.create(nombre="Uyuni", ciudad="Uyuni")

        # Dos terminales de La Paz hacia Oruro: horas sumadas, sin repetir y ordenadas.
        r1 = Ruta.objects.create(origen=lp_central, destino=oruro, precio_base=Decimal("50.00"))
        Horario.objects.create(ruta=r1, hora_salida=time(22, 0), dias_semana="L")
        Horario.objects.create(ruta=r1, hora_salida=time(8, 0), dias_semana="L")
        Horario.objects.create(ruta=r1, hora_salida=time(12, 0), dias_semana="L", activo=False)
        r2 = Ruta.objects.create(origen=lp_norte, destino=oruro)
        Horario.objects.create(ruta=r2, hora_salida=time(8, 0), dias_semana="M")
        Horario.objects.create(ruta=r2, hora_salida=time(15, 0), dias_semana="M")
        # Destino activo sin horarios: se lista igual.
        Ruta.objects.create(origen=lp_central, destino=potosi)
        # Ruta inactiva: no aparece.
        inactiva = Ruta.objects.create(origen=lp_central, destino=uyuni, activa=False)
        Horario.objects.create(ruta=inactiva, hora_salida=time(9, 0), dias_semana="L")
        # Origen solo con ruta inactiva: sin tarjeta.
        Ruta.objects.create(origen=uyuni, destino=oruro, activa=False)
        Ruta.objects.create(origen=sucre, destino=lp_central)

    def get(self):
        return self.client.get(reverse("core:salidas"))

    def test_agrupa_por_origen_y_destino(self):
        origenes = {o.ciudad: o for o in salidas_por_origen()}
        self.assertEqual(set(origenes), {"LA PAZ", "Chuquisaca"})
        destinos = {d.ciudad: d.horas for d in origenes["LA PAZ"].destinos}
        self.assertEqual(destinos, {"ORURO": [time(8, 0), time(15, 0), time(22, 0)], "Potosi": []})

    def test_imagen_por_ciudad_con_alias_y_sin_foto(self):
        casos = {"LA PAZ": "img/ciudades/la-paz.jpg", "Potosí": "img/ciudades/potosi.jpg",
                 "Chuquisaca": "img/ciudades/sucre.jpg", "Uyuni": None}
        for ciudad, esperado in casos.items():
            with self.subTest(ciudad=ciudad):
                self.assertEqual(OrigenSalidas(ciudad=ciudad).imagen, esperado)

    def test_imagenes_declaradas_existen(self):
        carpeta = Path(settings.BASE_DIR) / "static" / "img" / "ciudades"
        for slug in IMAGENES_CIUDADES:
            with self.subTest(slug=slug):
                self.assertTrue((carpeta / f"{slug}.jpg").is_file())

    def test_tarjeta_con_comprar_y_modal_de_horarios(self):
        respuesta = self.get()
        self.assertContains(respuesta, f'href="{reverse("ventas:buscar_viajes")}?origen=LA%20PAZ"')
        self.assertContains(respuesta, 'data-abrir-dialogo="horarios-1"')
        self.assertContains(respuesta, '<dialog id="horarios-1"')
        self.assertContains(respuesta, "08:00 - 15:00 - 22:00")
        self.assertContains(respuesta, "Sin horarios regulares publicados.")
        self.assertContains(respuesta, "img/ciudades/la-paz.jpg")
        self.assertNotContains(respuesta, "Uyuni")

    def test_comprar_preselecciona_el_origen_en_la_busqueda(self):
        respuesta = self.client.get(reverse("ventas:buscar_viajes"), {"origen": "LA PAZ"})
        self.assertEqual(respuesta.context["form"]["origen"].value(), "LA PAZ")
        self.assertTrue(respuesta.context["form"].is_valid())

    def test_sin_rutas_muestra_aviso(self):
        Ruta.objects.all().delete()
        self.assertContains(self.get(), "Aún no hay salidas publicadas.")


class NosotrosViewTests(TestCase):
    def test_muestra_historia_mision_y_vision(self):
        respuesta = self.client.get(reverse("core:nosotros"))
        self.assertTemplateUsed(respuesta, "core/nosotros.html")
        for texto in ("se creó en 1996", "Misión", "Visión"):
            with self.subTest(texto=texto):
                self.assertContains(respuesta, texto)
