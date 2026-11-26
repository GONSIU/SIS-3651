"""Codigos QR ficticios (proyecto academico): ninguno se conecta con un banco ni con
Impuestos Nacionales.

- QR de pago: empresa, monto y referencia. La referencia la genera la pagina al elegir QR
  y se guarda como Pago.referencia_externa.
- QR del boleto: los datos del pasaje, legibles al escanearlo sin conexion.

Se dibujan con reportlab, que el proyecto ya usa para los PDF de reportes: no hace falta
otra dependencia.
"""

import base64
import re
from decimal import Decimal

from django.utils import timezone
from reportlab.graphics import renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing

# Misma forma que genera static/js/pago_qr.js: "QR-" y 8 letras o digitos.
PATRON_REFERENCIA = re.compile(r"^QR-[A-Z0-9]{8}\Z")
MONTO_MAXIMO = Decimal("99999.99")
TAMANO_PUNTOS = 180
# Nombre que se lee al escanear. No se importa EMPRESA_FISCAL de views.py: views.py importa
# este modulo y seria un import circular.
EMPRESA_QR = "TRANS NASER S.R.L."


def svg_qr(texto: str, tamano: int = TAMANO_PUNTOS) -> str:
    """Documento SVG de un QR cuadrado de `tamano` puntos, con margen blanco alrededor."""
    widget = QrCodeWidget(texto, barBorder=2)
    x1, y1, x2, y2 = widget.getBounds()
    escala_x, escala_y = tamano / (x2 - x1), tamano / (y2 - y1)
    dibujo = Drawing(tamano, tamano, transform=[escala_x, 0, 0, escala_y, 0, 0])
    dibujo.add(widget)
    return renderSVG.drawToString(dibujo)


def data_uri_svg(svg: str) -> str:
    """Para incrustar el SVG en <img src=...> sin otra peticion al servidor."""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def contenido_pago_qr(monto: Decimal, referencia: str) -> str:
    """Texto que codifica el QR de pago. Formato propio y ficticio."""
    return f"{EMPRESA_QR}|PAGO DEMO|REF:{referencia}|MONTO:{monto:.2f} BOB"


def svg_pago_qr(monto: Decimal, referencia: str) -> str:
    return svg_qr(contenido_pago_qr(monto, referencia))


def contenido_boleto_qr(pasaje) -> str:
    """Datos del boleto, una linea por dato. Sin flechas ni simbolos: algunos lectores de
    QR no los muestran bien."""
    viaje = pasaje.viaje
    ruta = viaje.ruta
    salida = timezone.localtime(viaje.salida_programada)
    carril = f" CARRIL {viaje.horario.carril}" if viaje.horario.carril else ""
    pasajero = pasaje.nombre_pasajero + (f" CI {pasaje.cliente_ci}" if pasaje.cliente_ci else "")
    comprobante = getattr(pasaje, "comprobante", None)
    lineas = [
        EMPRESA_QR,
        f"BOLETO {pasaje.codigo_pasaje} ({pasaje.get_estado_display().upper()})",
        f"RUTA: {ruta.origen.ciudad} - {ruta.destino.ciudad}",
        f"SALIDA: {salida:%d/%m/%Y %H:%M}{carril}",
        f"ASIENTO: {pasaje.asiento_viaje.asiento.numero} BUS {viaje.bus.placa}",
        f"PASAJERO: {pasajero}",
        f"TOTAL: Bs {pasaje.precio:.2f}",
    ]
    if comprobante is not None:
        lineas.append(f"CONTROL: {comprobante.codigo_control}")
    return "\n".join(lineas)
