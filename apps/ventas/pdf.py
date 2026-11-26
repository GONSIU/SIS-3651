"""Boleto y comprobante en PDF (subflujo A1 de Emitir boleto y factura).

Se arma en memoria con reportlab platypus, como apps/reportes/pdf.py, y se descarga al
momento: Comprobante.archivo_pdf sigue vacio porque el PDF siempre se puede regenerar
con los datos del pasaje, y guardarlo duplicaria informacion."""

from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Pasaje
from .qr import contenido_boleto_qr

NAVY = colors.HexColor("#0a192f")
GRIS = colors.HexColor("#eeeef0")
LADO_QR = 3.5 * cm


def _texto(valor) -> str:
    """Escapa el marcado XML de Paragraph y cambia la flecha, que Helvetica no tiene."""
    return escape(str(valor)).replace("→", "->")


def _qr(texto: str) -> Drawing:
    widget = QrCodeWidget(texto, barBorder=2)
    x1, y1, x2, y2 = widget.getBounds()
    dibujo = Drawing(LADO_QR, LADO_QR, transform=[LADO_QR / (x2 - x1), 0, 0, LADO_QR / (y2 - y1), 0, 0])
    dibujo.add(widget)
    return dibujo


def _tabla(filas: list[list[str]]) -> Table:
    tabla = Table(filas, colWidths=[4 * cm, 8.5 * cm])
    tabla.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, GRIS]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return tabla


def pdf_boleto(pasaje: Pasaje, empresa: dict) -> bytes:
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("titulo", parent=estilos["Title"], textColor=NAVY, fontSize=15, spaceAfter=4)
    normal = ParagraphStyle("normal", parent=estilos["Normal"], fontSize=9, leading=12)
    aviso = ParagraphStyle("aviso", parent=normal, textColor=colors.HexColor("#b91c1c"))
    pie = ParagraphStyle("pie", parent=normal, fontSize=7, textColor=colors.grey, alignment=1)

    viaje = pasaje.viaje
    comprobante = getattr(pasaje, "comprobante", None)
    salida = timezone.localtime(viaje.salida_programada)
    es_reserva = pasaje.estado == "reservado"

    contenido = [
        Paragraph(_texto(empresa["razon_social"]), titulo),
        Paragraph(_texto(f"{empresa['sucursal']} - {empresa['punto_venta']} - {empresa['direccion']} - NIT {empresa['nit']}"), normal),
        Spacer(1, 0.3 * cm),
        Paragraph("<b>COMPROBANTE DE RESERVA</b>" if es_reserva else "<b>BOLETO DE VIAJE</b>", normal),
    ]
    if es_reserva:
        limite = timezone.localtime(pasaje.reservado_hasta)
        contenido.append(
            Paragraph(
                _texto(f"NO VALIDO PARA ABORDAR. Paga el saldo de Bs {pasaje.saldo} en ventanilla antes del {limite:%d/%m/%Y %H:%M}."),
                aviso,
            )
        )
    contenido.append(Spacer(1, 0.2 * cm))

    filas = [
        ["E-ticket", pasaje.codigo_pasaje],
        ["Estado", pasaje.get_estado_display()],
        ["Ruta", f"{viaje.ruta.origen.ciudad} - {viaje.ruta.destino.ciudad}"],
        ["Salida", f"{salida:%d/%m/%Y %H:%M}" + (f"  (carril {viaje.horario.carril})" if viaje.horario.carril else "")],
        ["Bus", f"{viaje.bus.placa} - {viaje.bus.nombre_tipo}"],
        ["Asiento", str(pasaje.asiento_viaje.asiento.numero)],
        ["Pasajero", pasaje.nombre_pasajero],
    ]
    if pasaje.cliente_ci:
        filas.append(["CI", pasaje.cliente_ci])
    if comprobante:
        filas.append(["Comprobante", f"{comprobante.get_tipo_display()} {comprobante.numero_comprobante}"])
        if comprobante.nit_cliente:
            filas += [["NIT/CI cliente", comprobante.nit_cliente], ["Razon social", comprobante.razon_social_cliente]]
        filas.append(["Codigo de control", comprobante.codigo_control or "-"])
    filas += [
        ["Total", f"Bs {pasaje.precio}"],
        ["Total pagado", f"Bs {pasaje.total_pagado}"],
    ]
    if pasaje.saldo:
        filas.append(["Saldo pendiente", f"Bs {pasaje.saldo}"])
    filas.append(["Emision", f"{timezone.localtime(pasaje.created_at):%d/%m/%Y %H:%M}"])
    contenido += [_tabla(filas), Spacer(1, 0.4 * cm), _qr(contenido_boleto_qr(pasaje)), Spacer(1, 0.3 * cm)]
    contenido.append(
        Paragraph(
            "NO REEMBOLSABLE. Documento de prueba generado con fines academicos: no tiene validez tributaria.",
            pie,
        )
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A5, leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        title=f"Boleto {pasaje.codigo_pasaje}", author=empresa["razon_social"],
    )
    doc.build(contenido)
    return buffer.getvalue()
