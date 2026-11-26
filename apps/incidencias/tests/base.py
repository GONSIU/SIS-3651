from decimal import Decimal

from apps.incidencias.models import Incidencia
from apps.usuarios.models import Usuario
from apps.ventas.models import Pasaje
from apps.ventas.tests.base import VentasTestCase


class IncidenciasTestCase(VentasTestCase):
    """Reusa el viaje, bus y vendedor de VentasTestCase y agrega supervisor y clientes."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.supervisor = Usuario.objects.create_user(
            "sup", rol="supervisor", terminal_asignado=cls.ruta.origen, first_name="Sara", last_name="Quispe"
        )
        cls.cliente = Usuario.objects.create_user("ana", rol="cliente", ci="1234567", first_name="Ana")
        cls.otro_cliente = Usuario.objects.create_user("beto", rol="cliente", ci="7654321")
        cls.pasaje = Pasaje.objects.create(
            viaje=cls.viaje, asiento_viaje=cls.asiento, cliente=cls.cliente, cliente_nombre="Ana",
            cliente_ci="1234567", canal="online", precio=Decimal("50"), estado="pagado",
        )

    def crear_incidencia(self, **kwargs) -> Incidencia:
        datos = {
            "categoria": "falla_mecanica", "titulo": "Falla de frenos", "descripcion": "Se detuvo en ruta.",
            "reportado_por": self.supervisor,
        }
        return Incidencia.objects.create(**{**datos, **kwargs})

    def crear_reclamo(self, **kwargs) -> Incidencia:
        datos = {"categoria": "reclamo", "reportado_por": self.cliente, "titulo": "Retraso", "descripcion": "Llego tarde."}
        return self.crear_incidencia(**{**datos, **kwargs})
