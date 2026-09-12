import uuid


def generar_codigo(prefijo="COD"):
    """Genera un código único legible (ej. para pasajes, encomiendas, comprobantes)."""
    return f"{prefijo}-{uuid.uuid4().hex[:8].upper()}"
