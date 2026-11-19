"""PDF del reporte de ventas con reportlab (ya estaba en requirements/base.txt).

Se arma con platypus (flujo de parrafos y tablas) en memoria y se devuelve como bytes:
no se guarda ningun archivo en el servidor."""
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .services import ReporteVentas

NAVY = colors.HexColor("#0a192f")
GRIS = colors.HexColor("#eeeef0")


def bs(valor: Decimal) -> str:
    return f"Bs. {valor:,.2f}"


def sin_flecha(texto: str) -> str:
    """Las fuentes base de reportlab (Helvetica) no tienen la flecha: se dibujaria un cuadro."""
    return texto.replace("\u2192", "->")


def para_parrafo(texto: str) -> str:
    """Paragraph interpreta marcado XML: un "&" o "<" en un nombre se escapa. Las celdas
    de Table son texto plano y no lo necesitan."""
    return escape(sin_flecha(texto))


def _tabla(datos: list[list[str]], anchos: list[float], alinear_desde: int = 1) -> Table:
    tabla = Table(datos, colWidths=anchos, repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (alinear_desde, 0), (-1, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return tabla


def pdf_reporte_ventas(reporte: ReporteVentas, filtros_texto: str) -> bytes:
    estilos = getSampleStyleSheet()
    estilos["Title"].textColor = NAVY
    periodo = reporte.periodo
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title="Reporte de ventas - Trans Naser",
    )

    variacion = f" ({reporte.variacion_texto})" if reporte.variacion_texto else ""

    contenido = [
        Paragraph("Trans Naser - Reporte de ventas", estilos["Title"]),
        Paragraph(
            f"Del {periodo.desde:%d/%m/%Y} al {periodo.hasta:%d/%m/%Y}. {para_parrafo(filtros_texto)}", estilos["Normal"]
        ),
        Spacer(1, 0.5 * cm),
        _tabla(
            [
                ["Resumen", "Valor"],
                ["Pasajes vendidos", f"{reporte.pasajes_vendidos}{variacion}"],
                ["Ingresos pasajes (cobrado)", bs(reporte.ingresos_pasajes)],
                ["Encomiendas registradas", str(reporte.encomiendas)],
                ["Ingresos encomiendas", bs(reporte.ingresos_encomiendas)],
                ["Ingresos totales", bs(reporte.ingresos_totales)],
            ],
            [10 * cm, 7 * cm],
        ),
        Spacer(1, 0.5 * cm),
        Paragraph("Ventas por ruta", estilos["Heading2"]),
    ]
    if reporte.rutas:
        contenido.append(_tabla([["Ruta", "Ingresos"]] + [[sin_flecha(r.ruta), bs(r.total)] for r in reporte.rutas], [10 * cm, 7 * cm]))
    else:
        contenido.append(Paragraph("Sin ventas en el periodo.", estilos["Normal"]))

    contenido += [Spacer(1, 0.5 * cm), Paragraph("Detalle diario", estilos["Heading2"])]
    if reporte.hay_movimiento:
        contenido.append(
            _tabla(
                [["Fecha", "Pasajes", "Encomiendas", "Ingresos totales"]]
                + [[f"{f.fecha:%d/%m/%Y}", str(f.pasajes), str(f.encomiendas), bs(f.ingresos)] for f in reporte.filas],
                [4.5 * cm, 3.5 * cm, 4 * cm, 5 * cm],
            )
        )
    else:
        contenido.append(Paragraph("Sin ventas ni encomiendas en el periodo.", estilos["Normal"]))

    doc.build(contenido)
    return buffer.getvalue()
