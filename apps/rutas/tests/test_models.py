from datetime import date, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.rutas.forms import HorarioForm
from apps.rutas.models import Horario, Ruta, Terminal, validar_dias_semana


class TerminalTests(TestCase):
    def test_normaliza_espacios(self):
        terminal = Terminal(nombre="  Terminal   Bimodal ", ciudad="Santa  Cruz")
        terminal.full_clean()
        self.assertEqual(terminal.nombre, "Terminal Bimodal")
        self.assertEqual(terminal.ciudad, "Santa Cruz")

    def test_rechaza_nombre_con_digitos(self):
        with self.assertRaises(ValidationError) as error:
            Terminal(nombre="Terminal 2", ciudad="Oruro").full_clean()
        self.assertIn("nombre", error.exception.message_dict)

    def test_unicidad_sin_distinguir_mayusculas(self):
        Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        with self.assertRaises(ValidationError):
            Terminal(nombre="BIMODAL", ciudad="la paz").full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Terminal.objects.create(nombre="BIMODAL", ciudad="la paz")

    def test_mismo_nombre_en_otra_ciudad_es_valido(self):
        Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        Terminal(nombre="Bimodal", ciudad="Oruro").full_clean()


class RutaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.origen = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        cls.destino = Terminal.objects.create(nombre="Central", ciudad="Oruro")

    def ruta(self, **kwargs) -> Ruta:
        return Ruta(**{"origen": self.origen, "destino": self.destino, **kwargs})

    def test_limites_de_distancia(self):
        self.ruta(distancia_km=Decimal("0.01")).full_clean()
        self.ruta(distancia_km=None).full_clean()
        for valor in (Decimal("0"), Decimal("-1")):
            with self.subTest(valor=valor), self.assertRaises(ValidationError) as error:
                self.ruta(distancia_km=valor).full_clean()
            self.assertIn("distancia_km", error.exception.message_dict)

    def test_limites_de_duracion(self):
        self.ruta(duracion_minutos=1).full_clean()
        self.ruta(duracion_minutos=None).full_clean()
        with self.assertRaises(ValidationError) as error:
            self.ruta(duracion_minutos=0).full_clean()
        self.assertIn("duracion_minutos", error.exception.message_dict)

    def test_constraints_en_base_de_datos(self):
        casos = [
            {"distancia_km": Decimal("0")},
            {"duracion_minutos": 0},
            {"destino": self.origen},
        ]
        for datos in casos:
            with self.subTest(datos=datos):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.ruta(**datos).save()

    def test_origen_y_destino_iguales_fallan_en_full_clean(self):
        with self.assertRaises(ValidationError):
            self.ruta(destino=self.origen).full_clean()

    def test_ruta_duplicada(self):
        self.ruta().save()
        with self.assertRaises(ValidationError):
            self.ruta().full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.ruta().save()

    def test_ruta_inversa_es_valida(self):
        self.ruta().save()
        Ruta(origen=self.destino, destino=self.origen).full_clean()


class HorarioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        origen = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        destino = Terminal.objects.create(nombre="Central", ciudad="Oruro")
        cls.ruta = Ruta.objects.create(origen=origen, destino=destino)

    def test_validar_dias_semana(self):
        for valor in ("L", "L,M,X,J,V,S,D", "D,L"):
            with self.subTest(valor=valor):
                validar_dias_semana(valor)
        for valor in ("", "A", "L,", "L,L", "L M", "l", "L, M"):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                validar_dias_semana(valor)

    def test_opera_el(self):
        horario = Horario(ruta=self.ruta, hora_salida=time(8), dias_semana="L,S")
        lunes = date(2026, 11, 2)
        martes = date(2026, 11, 3)
        sabado = date(2026, 11, 7)
        domingo = date(2026, 11, 8)
        self.assertTrue(horario.opera_el(lunes))
        self.assertFalse(horario.opera_el(martes))
        self.assertTrue(horario.opera_el(sabado))
        self.assertFalse(horario.opera_el(domingo))

    def formulario(self, dias_semana: str) -> HorarioForm:
        return HorarioForm(
            data={"ruta": self.ruta.pk, "hora_salida": "08:00", "dias_semana": dias_semana}
        )

    def test_formulario_normaliza_dias(self):
        form = self.formulario("v, l ,m")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().dias_semana, "L,M,V")

    def test_formulario_acepta_semana_completa_con_espacios(self):
        form = self.formulario("l, m, x, j, v, s, d")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().dias_semana, "L,M,X,J,V,S,D")

    def test_formulario_rechaza_dias_repetidos(self):
        form = self.formulario("L,L")
        self.assertFalse(form.is_valid())
        self.assertIn("dias_semana", form.errors)
