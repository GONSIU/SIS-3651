"""Busqueda del encabezado: pasajes y encomiendas por codigo, CI o nombre.

Que se busca segun el texto:
- Codigo (PSJ-..., ENC-...): coincidencia parcial en codigo_pasaje o codigo_guia.
- CI (5 a 10 digitos, con complemento opcional como 1234567-1A): CI exacto del pasajero (la
  cuenta o el CI escrito en ventanilla) y del remitente o destinatario.
- Otro texto: nombre del pasajero, remitente o destinatario (contiene).
"""

from dataclasses import dataclass, field

from django.db.models import Q

from apps.core.validators import normalizar_ci, validar_ci
from apps.encomiendas.models import Encomienda
from apps.ventas.models import Pasaje

LARGO_MINIMO = 3
MAX_RESULTADOS = 20
# Prefijos de generar_codigo() en Pasaje.save() y Encomienda.save().
PREFIJO_PASAJE = "PSJ-"
PREFIJO_ENCOMIENDA = "ENC-"


@dataclass
class Resultados:
    texto: str
    criterio: str = ""  # "codigo", "ci" o "nombre"; vacio si el texto es muy corto
    pasajes: list = field(default_factory=list)
    encomiendas: list = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.pasajes) + len(self.encomiendas)

    @property
    def unico(self):
        """El unico resultado de una busqueda por codigo, para ir directo a el."""
        if self.criterio == "codigo" and self.total == 1:
            return (self.pasajes or self.encomiendas)[0]
        return None


def _filtros(texto: str) -> tuple[str, Q, Q]:
    mayusculas = texto.upper()
    if mayusculas.startswith((PREFIJO_PASAJE, PREFIJO_ENCOMIENDA)):
        # Un codigo PSJ- no puede ser de una encomienda y al reves.
        es_pasaje = mayusculas.startswith(PREFIJO_PASAJE)
        nada = Q(pk__in=[])
        return (
            "codigo",
            Q(codigo_pasaje__icontains=mayusculas) if es_pasaje else nada,
            nada if es_pasaje else Q(codigo_guia__icontains=mayusculas),
        )
    ci = normalizar_ci(texto)
    # Se reutiliza la regex de validar_ci: un CI se reconoce igual que se valida.
    if validar_ci.regex.match(ci):
        return (
            "ci",
            Q(cliente_ci=ci) | Q(cliente__ci=ci),
            Q(remitente_ci=ci) | Q(destinatario_ci=ci),
        )
    return (
        "nombre",
        Q(cliente_nombre__icontains=texto)
        | Q(cliente__first_name__icontains=texto)
        | Q(cliente__last_name__icontains=texto),
        Q(remitente_nombre__icontains=texto) | Q(destinatario_nombre__icontains=texto),
    )


def buscar(texto: str) -> Resultados:
    """Hasta MAX_RESULTADOS pasajes y encomiendas, los mas recientes primero."""
    texto = " ".join(texto.split())
    resultados = Resultados(texto=texto)
    if len(texto) < LARGO_MINIMO:
        return resultados

    resultados.criterio, filtro_pasaje, filtro_encomienda = _filtros(texto)
    resultados.pasajes = list(
        Pasaje.objects.filter(filtro_pasaje)
        .select_related("cliente", "viaje__ruta__origen", "viaje__ruta__destino", "viaje__horario")
        .order_by("-created_at")[:MAX_RESULTADOS]
    )
    resultados.encomiendas = list(
        Encomienda.objects.filter(filtro_encomienda)
        .select_related("viaje__ruta__origen", "viaje__ruta__destino")
        .order_by("-created_at")[:MAX_RESULTADOS]
    )
    return resultados
