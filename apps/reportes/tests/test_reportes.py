from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.reportes.services import Periodo, reporte_encomiendas, reporte_ocupacion, reporte_ventas

from .base import DIA_1, DIA_2, ReportesTestCase

DOS_DIAS = Periodo(DIA_1, DIA_2, "personalizado")
RANGO = {"desde": DIA_1.isoformat(), "hasta": DIA_2.isoformat()}


class ReporteVentasTests(ReportesTestCase):
    def setUp(self):
        self.viaje_ida = self.crear_viaje()
        self.viaje_vuelta = self.crear_viaje(ruta=self.ruta_vuelta)

    def cargar_datos(self):
        self.crear_pasaje(self.viaje_ida, DIA_1)  # 50
        self.crear_pasaje(self.viaje_ida, DIA_2, estado="usado", pagos=("20.00", "30.00"))  # 50
        self.crear_pasaje(self.viaje_vuelta, DIA_2, precio="80.00", pagos=("80.00",))  # 80
        # Reserva con anticipo: no cuenta como vendida, pero su anticipo es dinero cobrado.
        self.crear_pasaje(self.viaje_vuelta, DIA_2, estado="reservado", pagos=("15.00",))
        # Cancelada: tampoco cuenta como vendida; su anticipo no se devuelve.
        self.crear_pasaje(self.viaje_vuelta, DIA_1, estado="cancelado", pagos=("10.00",))
        # Fuera del periodo: no cuenta.
        self.crear_pasaje(self.viaje_ida, DIA_2 + timedelta(days=1))
        self.crear_encomienda(self.viaje_ida, DIA_1, precio="20.00")
        self.crear_encomienda(self.viaje_vuelta, DIA_2, precio="35.50", estado="entregado")

    def test_resumen_con_datos(self):
        self.cargar_datos()
        reporte = reporte_ventas(DOS_DIAS)
        self.assertEqual(reporte.pasajes_vendidos, 3)
        self.assertEqual(reporte.ingresos_pasajes, Decimal("205.00"))  # 50+20+30+80+15+10
        self.assertEqual(reporte.encomiendas, 2)
        self.assertEqual(reporte.ingresos_encomiendas, Decimal("55.50"))
        self.assertEqual(reporte.ingresos_totales, Decimal("260.50"))

    def test_rutas_ordenadas_por_ingreso_con_barra_relativa(self):
        self.cargar_datos()
        rutas = reporte_ventas(DOS_DIAS).rutas
        self.assertEqual([r.ruta for r in rutas], ["Oruro → La Paz", "La Paz → Oruro"])
        self.assertEqual([r.total for r in rutas], [Decimal("105.00"), Decimal("100.00")])
        self.assertEqual(rutas[0].ancho_pct, 100)
        self.assertAlmostEqual(rutas[1].ancho_pct, 100 / 105 * 100)

    def test_tabla_una_fila_por_dia(self):
        self.cargar_datos()
        filas = reporte_ventas(DOS_DIAS).filas
        self.assertEqual([f.fecha for f in filas], [DIA_2, DIA_1])
        self.assertEqual([(f.pasajes, f.encomiendas) for f in filas], [(2, 1), (1, 1)])
        self.assertEqual([f.ingresos for f in filas], [Decimal("180.50"), Decimal("80.00")])

    def test_filtro_por_ruta_y_por_terminal_de_origen(self):
        self.cargar_datos()
        por_ruta = reporte_ventas(DOS_DIAS, ruta=self.ruta_ida)
        por_terminal = reporte_ventas(DOS_DIAS, terminal=self.lp)
        for reporte in (por_ruta, por_terminal):
            with self.subTest(reporte=reporte):
                self.assertEqual(reporte.pasajes_vendidos, 2)
                self.assertEqual(reporte.ingresos_pasajes, Decimal("100.00"))
                self.assertEqual(reporte.encomiendas, 1)

    def test_variacion_contra_el_periodo_anterior(self):
        self.cargar_datos()
        anterior = DIA_1 - timedelta(days=1)  # DOS_DIAS.anterior() = 7 y 8 de marzo
        otro_viaje = self.crear_viaje(fecha_salida=anterior)  # el bus tiene solo 4 asientos
        self.crear_pasaje(otro_viaje, anterior)
        self.crear_pasaje(otro_viaje, anterior)
        reporte = reporte_ventas(DOS_DIAS)
        self.assertEqual(reporte.variacion_pasajes_pct, 50.0)
        self.assertEqual(reporte.variacion_texto, "+50% vs periodo anterior")

    def test_sin_periodo_anterior_no_hay_porcentaje(self):
        self.cargar_datos()
        reporte = reporte_ventas(DOS_DIAS)
        self.assertIsNone(reporte.variacion_pasajes_pct)
        self.assertEqual(reporte.variacion_texto, "")

    def test_sin_datos_todo_en_cero(self):
        reporte = reporte_ventas(DOS_DIAS)
        self.assertEqual((reporte.pasajes_vendidos, reporte.encomiendas), (0, 0))
        self.assertEqual(reporte.ingresos_totales, Decimal("0"))
        self.assertEqual(reporte.rutas, [])
        self.assertFalse(reporte.hay_movimiento)
        self.assertIsNone(reporte.variacion_pasajes_pct)
        self.assertTrue(all(f.pasajes == 0 and f.ingresos == 0 for f in reporte.filas))

    def test_consultas_fijas_sin_n_mas_1(self):
        with CaptureQueriesContext(connection) as vacio:
            reporte_ventas(DOS_DIAS)
        self.cargar_datos()
        with CaptureQueriesContext(connection) as con_datos:
            reporte_ventas(DOS_DIAS)
        self.assertEqual(len(con_datos), len(vacio))

    def test_vista_con_datos(self):
        self.cargar_datos()
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("reportes:listado"), RANGO)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Bs. 205.00")
        self.assertContains(respuesta, "Oruro → La Paz")
        self.assertContains(respuesta, f'{reverse("reportes:ventas_pdf")}?desde=')
        self.assertNotContains(respuesta, "1,248")  # nada de la maqueta

    def test_vista_sin_datos_muestra_mensajes(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("reportes:listado"), RANGO)
        self.assertContains(respuesta, "No hubo cobros de pasajes en este período.")
        self.assertContains(respuesta, "Sin ventas ni encomiendas en este período.")
        self.assertNotContains(respuesta, "trending_up")

    def test_pestanas_conservan_la_ruta(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("reportes:listado"), {"periodo": "semanal", "ruta": self.ruta_ida.pk})
        self.assertContains(respuesta, f'href="?periodo=diario&amp;ruta={self.ruta_ida.pk}"')
        self.assertEqual(respuesta.context["periodo"].tipo, "semanal")

    def test_rango_invalido_muestra_error_y_usa_el_mes(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("reportes:listado"), {"desde": DIA_2.isoformat(), "hasta": DIA_1.isoformat()})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "La fecha desde no puede ser posterior a la fecha hasta.")
        self.assertEqual(respuesta.context["periodo"].tipo, "mensual")


class ExportarVentasPdfTests(ReportesTestCase):
    def test_pdf_con_y_sin_datos(self):
        self.client.force_login(self.usuario)
        url = reverse("reportes:ventas_pdf")
        for con_datos in (False, True):
            if con_datos:
                viaje = self.crear_viaje()
                self.crear_pasaje(viaje, DIA_1)
                self.crear_encomienda(viaje, DIA_2)
            with self.subTest(con_datos=con_datos):
                respuesta = self.client.get(url, {**RANGO, "ruta": self.ruta_ida.pk})
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta["Content-Type"], "application/pdf")
                self.assertIn("reporte-ventas-20260309-20260310.pdf", respuesta["Content-Disposition"])
                self.assertTrue(respuesta.content.startswith(b"%PDF"))


class ReporteOcupacionTests(ReportesTestCase):
    def test_ocupacion_con_datos(self):
        lleno = self.crear_viaje(fecha_salida=DIA_1)
        for _ in range(3):
            self.crear_pasaje(lleno, DIA_1)
        medio = self.crear_viaje(ruta=self.ruta_vuelta, fecha_salida=DIA_2)
        self.crear_pasaje(medio, DIA_1)
        self.crear_pasaje(medio, DIA_1, estado="reservado", pagos=("15.00",))
        cancelado = self.crear_viaje(fecha_salida=DIA_2, estado="cancelado")
        self.crear_pasaje(cancelado, DIA_1)

        reporte = reporte_ocupacion(DOS_DIAS)
        self.assertEqual([v.pk for v in reporte.viajes], [lleno.pk, medio.pk])
        self.assertEqual([v.ocupacion_pct for v in reporte.viajes], [75.0, 25.0])
        self.assertEqual((reporte.capacidad, reporte.vendidos, reporte.reservados), (8, 4, 1))
        self.assertEqual(reporte.ocupacion_pct, 50.0)
        self.assertEqual(len(reporte_ocupacion(DOS_DIAS, ruta=self.ruta_vuelta).viajes), 1)

    def test_viaje_sin_asientos_no_divide_por_cero(self):
        from apps.viajes.models import Viaje

        Viaje.objects.create(ruta=self.ruta_ida, horario=self.horario_ida, bus=self.bus, fecha_salida=DIA_1)
        reporte = reporte_ocupacion(DOS_DIAS)
        self.assertIsNone(reporte.viajes[0].ocupacion_pct)
        self.assertIsNone(reporte.ocupacion_pct)

    def test_sin_viajes(self):
        reporte = reporte_ocupacion(DOS_DIAS)
        self.assertEqual(reporte.viajes, [])
        self.assertIsNone(reporte.ocupacion_pct)
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(reverse("reportes:ocupacion"), RANGO), "No hay viajes con salida en este período.")

    def test_vista_sin_n_mas_1(self):
        self.client.force_login(self.usuario)
        self.crear_viaje(fecha_salida=DIA_1)
        with CaptureQueriesContext(connection) as uno:
            self.client.get(reverse("reportes:ocupacion"), RANGO)
        self.crear_viaje(fecha_salida=DIA_2)
        self.crear_viaje(ruta=self.ruta_vuelta, fecha_salida=DIA_2)
        with CaptureQueriesContext(connection) as tres:
            respuesta = self.client.get(reverse("reportes:ocupacion"), RANGO)
        self.assertEqual(len(respuesta.context["reporte"].viajes), 3)
        self.assertEqual(len(tres), len(uno))


class ReporteEncomiendasTests(ReportesTestCase):
    def test_por_estado_con_datos(self):
        viaje = self.crear_viaje()
        for estado in ("registrado", "registrado", "en_destino", "entregado"):
            self.crear_encomienda(viaje, DIA_1, estado=estado)
        self.crear_encomienda(viaje, DIA_2 + timedelta(days=1), estado="entregado")  # fuera del periodo

        reporte = reporte_encomiendas(DOS_DIAS)
        self.assertEqual(reporte.total, 4)
        self.assertEqual(reporte.despachadas, 1)
        self.assertEqual(reporte.despachadas_pct, 25.0)
        self.assertEqual(
            [(e.estado, e.cantidad) for e in reporte.estados],
            [("registrado", 2), ("en_destino", 1), ("entregado", 1), ("extraviado", 0)],
        )

    def test_sin_encomiendas(self):
        reporte = reporte_encomiendas(DOS_DIAS)
        self.assertEqual((reporte.total, reporte.despachadas), (0, 0))
        self.assertIsNone(reporte.despachadas_pct)
        self.assertTrue(all(e.cantidad == 0 and e.pct is None for e in reporte.estados))
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("reportes:encomiendas"), RANGO)
        self.assertContains(respuesta, "No se registraron encomiendas en este período.")
