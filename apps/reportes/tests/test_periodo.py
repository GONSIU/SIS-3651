from datetime import date

from django.test import SimpleTestCase, TestCase

from apps.reportes.forms import ReporteFiltroForm
from apps.reportes.services import Periodo, periodo_predefinido, porcentaje, variacion_pct

HOY = date(2026, 3, 18)


class PeriodoTests(SimpleTestCase):
    def test_predefinidos(self):
        casos = {
            "diario": (date(2026, 3, 18), date(2026, 3, 18)),
            "semanal": (date(2026, 3, 12), date(2026, 3, 18)),
            "mensual": (date(2026, 3, 1), date(2026, 3, 18)),
            "otro": (date(2026, 3, 1), date(2026, 3, 18)),  # desconocido -> mes actual
        }
        for tipo, (desde, hasta) in casos.items():
            with self.subTest(tipo=tipo):
                periodo = periodo_predefinido(tipo, HOY)
                self.assertEqual((periodo.desde, periodo.hasta), (desde, hasta))

    def test_periodo_anterior(self):
        casos = [
            (periodo_predefinido("diario", HOY), (date(2026, 3, 17), date(2026, 3, 17))),
            (periodo_predefinido("semanal", HOY), (date(2026, 3, 5), date(2026, 3, 11))),
            (periodo_predefinido("mensual", HOY), (date(2026, 2, 1), date(2026, 2, 18))),
            # 31 de marzo: febrero no tiene 31, se corta en su ultimo dia.
            (periodo_predefinido("mensual", date(2026, 3, 31)), (date(2026, 2, 1), date(2026, 2, 28))),
            # Enero: el anterior es diciembre del ano pasado.
            (periodo_predefinido("mensual", date(2026, 1, 10)), (date(2025, 12, 1), date(2025, 12, 10))),
            (Periodo(date(2026, 3, 10), date(2026, 3, 12), "personalizado"), (date(2026, 3, 7), date(2026, 3, 9))),
        ]
        for periodo, (desde, hasta) in casos:
            with self.subTest(periodo=periodo):
                anterior = periodo.anterior()
                self.assertEqual((anterior.desde, anterior.hasta), (desde, hasta))

    def test_fechas_del_mas_reciente_al_mas_antiguo(self):
        periodo = Periodo(date(2026, 3, 9), date(2026, 3, 11), "personalizado")
        self.assertEqual(periodo.fechas(), [date(2026, 3, 11), date(2026, 3, 10), date(2026, 3, 9)])

    def test_porcentajes_sin_division_por_cero(self):
        self.assertIsNone(porcentaje(3, 0))
        self.assertEqual(porcentaje(1, 4), 25.0)
        self.assertIsNone(variacion_pct(5, 0))
        self.assertEqual(variacion_pct(6, 4), 50.0)
        self.assertEqual(variacion_pct(0, 4), -100.0)


class ReporteFiltroFormTests(TestCase):
    def test_sin_datos_es_el_mes_actual(self):
        periodo = ReporteFiltroForm().periodo_elegido(HOY)
        self.assertEqual((periodo.desde, periodo.hasta, periodo.tipo), (date(2026, 3, 1), HOY, "mensual"))

    def test_rango_personalizado_tiene_prioridad(self):
        form = ReporteFiltroForm({"periodo": "diario", "desde": "2026-01-05", "hasta": "2026-01-20"})
        periodo = form.periodo_elegido(HOY)
        self.assertEqual((periodo.desde, periodo.hasta, periodo.tipo), (date(2026, 1, 5), date(2026, 1, 20), "personalizado"))

    def test_rangos_invalidos_caen_al_mes_actual(self):
        casos = {
            "solo desde": {"desde": "2026-01-05"},
            "desde > hasta": {"desde": "2026-01-20", "hasta": "2026-01-05"},
            "mas de un ano": {"desde": "2024-01-01", "hasta": "2026-01-01"},
            "fecha mal escrita": {"desde": "2026-13-40", "hasta": "2026-01-05"},
            "periodo desconocido": {"periodo": "anual"},
        }
        for nombre, datos in casos.items():
            with self.subTest(caso=nombre):
                form = ReporteFiltroForm(datos)
                self.assertFalse(form.is_valid())
                self.assertEqual(form.periodo_elegido(HOY).tipo, "mensual")
                self.assertEqual(form.filtros(), {"ruta": None, "terminal": None})
