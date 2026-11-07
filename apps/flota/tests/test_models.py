from decimal import Decimal
from importlib import import_module

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.flota.forms import BusForm
from apps.flota.models import Asiento, Bus


def datos_bus(**kwargs) -> dict:
    return {
        "placa": "1234ABC",
        "nombre_tipo": "Semicama",
        "capacidad_pasajeros": 40,
        "capacidad_carga_kg": Decimal("500"),
        **kwargs,
    }


class BusTests(TestCase):
    def test_normaliza_placa_al_guardar_desde_formulario(self):
        form = BusForm(data={**datos_bus(placa="1234-abc"), "pisos": 1, "estado": "activo"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().placa, "1234ABC")

    def test_formulario_detecta_placa_duplicada_con_otro_formato(self):
        Bus.objects.create(**datos_bus())
        form = BusForm(data={**datos_bus(placa="1234-abc"), "pisos": 1, "estado": "activo"})
        self.assertFalse(form.is_valid())
        self.assertIn("placa", form.errors)

    def test_rechaza_placa_invalida(self):
        with self.assertRaises(ValidationError) as error:
            Bus(**datos_bus(placa="ABC")).full_clean()
        self.assertIn("placa", error.exception.message_dict)

    def test_rechaza_tipo_fuera_de_choices(self):
        with self.assertRaises(ValidationError) as error:
            Bus(**datos_bus(nombre_tipo="leito")).full_clean()
        self.assertIn("nombre_tipo", error.exception.message_dict)

    def test_limites_de_capacidad_pasajeros(self):
        for valor in (1, 80):
            with self.subTest(valor=valor):
                Bus(**datos_bus(capacidad_pasajeros=valor)).full_clean()
        for valor in (0, 81, -1):
            with self.subTest(valor=valor), self.assertRaises(ValidationError) as error:
                Bus(**datos_bus(capacidad_pasajeros=valor)).full_clean()
            self.assertIn("capacidad_pasajeros", error.exception.message_dict)

    def test_limites_de_capacidad_carga(self):
        Bus(**datos_bus(capacidad_carga_kg=Decimal("0"))).full_clean()
        with self.assertRaises(ValidationError) as error:
            Bus(**datos_bus(capacidad_carga_kg=Decimal("-0.01"))).full_clean()
        self.assertIn("capacidad_carga_kg", error.exception.message_dict)

    def test_constraints_en_base_de_datos(self):
        casos = [
            {"capacidad_pasajeros": 0},
            {"capacidad_pasajeros": 81},
            {"capacidad_carga_kg": Decimal("-1")},
        ]
        for datos in casos:
            with self.subTest(datos=datos):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Bus.objects.create(**datos_bus(**datos))


class AsientoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.bus = Bus.objects.create(**datos_bus(pisos=1))

    def asiento(self, **kwargs) -> Asiento:
        return Asiento(**{"bus": self.bus, "numero": "1", **kwargs})

    def test_limites_validos(self):
        for datos in ({"fila": 1, "columna": 1}, {"fila": None, "columna": None}, {"columna": 4}):
            with self.subTest(datos=datos):
                self.asiento(**datos).full_clean()

    def test_limites_invalidos(self):
        casos = [("fila", 0), ("columna", 0), ("columna", 5), ("piso", 0)]
        for campo, valor in casos:
            with self.subTest(campo=campo, valor=valor):
                with self.assertRaises(ValidationError) as error:
                    self.asiento(**{campo: valor}).full_clean()
                self.assertIn(campo, error.exception.message_dict)

    def test_constraints_en_base_de_datos(self):
        for datos in ({"fila": 0}, {"columna": 5}, {"piso": 0}):
            with self.subTest(datos=datos):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.asiento(**datos).save()

    def test_piso_no_puede_superar_los_pisos_del_bus(self):
        with self.assertRaises(ValidationError) as error:
            self.asiento(piso=2).full_clean()
        self.assertIn("piso", error.exception.message_dict)

    def test_sin_bus_no_falla_con_excepcion_inesperada(self):
        with self.assertRaises(ValidationError) as error:
            Asiento(numero="1", piso=2).full_clean()
        self.assertIn("bus", error.exception.message_dict)

    def test_crear_asientos_cumple_las_reglas(self):
        for nombre_tipo in ("Leito", "Cama", "Semicama"):
            bus = Bus.objects.create(
                **datos_bus(placa=f"{len(nombre_tipo)}234ABC", nombre_tipo=nombre_tipo, pisos=2, capacidad_pasajeros=80)
            )
            bus.crear_asientos()
            self.assertEqual(bus.asientos.count(), 80)
            for asiento in bus.asientos.all():
                asiento.full_clean()


class MigracionNormalizarBusesTests(TestCase):
    def test_normaliza_placas_y_tipos(self):
        # Con queryset.update se evita pasar por las reglas y se simulan datos antiguos.
        bus = Bus.objects.create(**datos_bus(placa="2378KLP"))
        otro = Bus.objects.create(**datos_bus(placa="5555ASM"))
        Bus.objects.filter(pk=bus.pk).update(placa="2378-klp", nombre_tipo="semicama")
        Bus.objects.filter(pk=otro.pk).update(placa="5555 asm", nombre_tipo="CAMA")

        migracion = import_module("apps.flota.migrations.0004_normalizar_placa_y_tipo")
        migracion.normalizar_buses(django_apps, None)

        bus.refresh_from_db()
        otro.refresh_from_db()
        self.assertEqual((bus.placa, bus.nombre_tipo), ("2378KLP", "Semicama"))
        self.assertEqual((otro.placa, otro.nombre_tipo), ("5555ASM", "Cama"))
