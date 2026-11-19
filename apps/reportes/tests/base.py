from datetime import date, datetime, time
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.encomiendas.models import Encomienda
from apps.flota.models import Bus
from apps.rutas.models import DIAS_VALIDOS, Horario, Ruta, Terminal
from apps.usuarios.models import Usuario
from apps.ventas.models import Pago, Pasaje
from apps.viajes.models import Viaje

# Fechas fijas: los servicios reciben el periodo, asi los tests no dependen de hoy.
DIA_1 = date(2026, 3, 9)
DIA_2 = date(2026, 3, 10)


def momento(dia: date, hora: int = 12) -> datetime:
    return timezone.make_aware(datetime.combine(dia, time(hora)))


class ReportesTestCase(TestCase):
    """Dos rutas (La Paz -> Oruro y Oruro -> La Paz), un bus de 4 asientos y helpers
    que fijan created_at, porque auto_now_add no deja elegir la fecha al crear."""

    @classmethod
    def setUpTestData(cls):
        cls.lp = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        cls.oruro = Terminal.objects.create(nombre="Central", ciudad="Oruro")
        cls.ruta_ida = Ruta.objects.create(origen=cls.lp, destino=cls.oruro)
        cls.ruta_vuelta = Ruta.objects.create(origen=cls.oruro, destino=cls.lp)
        dias = ",".join(DIAS_VALIDOS)
        cls.horario_ida = Horario.objects.create(ruta=cls.ruta_ida, hora_salida=time(8), dias_semana=dias)
        cls.horario_vuelta = Horario.objects.create(ruta=cls.ruta_vuelta, hora_salida=time(20), dias_semana=dias)
        cls.bus = Bus.objects.create(placa="1234ABC", nombre_tipo="Semicama", capacidad_pasajeros=4, capacidad_carga_kg=500)
        cls.bus.crear_asientos()
        cls.usuario = Usuario.objects.create_user("supervisor", rol="supervisor", terminal_asignado=cls.lp)

    @classmethod
    def crear_viaje(cls, ruta=None, fecha_salida=DIA_2, **kwargs) -> Viaje:
        ruta = ruta or cls.ruta_ida
        horario = cls.horario_ida if ruta == cls.ruta_ida else cls.horario_vuelta
        viaje = Viaje.objects.create(ruta=ruta, horario=horario, bus=cls.bus, fecha_salida=fecha_salida, **kwargs)
        viaje.crear_asientos_desde_bus()
        return viaje

    @staticmethod
    def crear_pasaje(viaje, dia: date, estado: str = "pagado", precio: str = "50.00", pagos=("50.00",)) -> Pasaje:
        """Pasaje en el siguiente asiento libre, con sus pagos; todo con fecha `dia`."""
        asiento = viaje.asientos_viaje.filter(estado="disponible").first()
        asiento.estado = "reservado" if estado == "reservado" else "vendido"
        asiento.save(update_fields=["estado"])
        pasaje = Pasaje.objects.create(
            viaje=viaje, asiento_viaje=asiento, canal="ventanilla", precio=Decimal(precio), estado=estado,
            cliente_nombre="Ana Quispe", cliente_ci="1234567",
        )
        for monto in pagos:
            Pago.objects.create(pasaje=pasaje, metodo="qr", monto=Decimal(monto))
        Pasaje.objects.filter(pk=pasaje.pk).update(created_at=momento(dia))
        Pago.objects.filter(pasaje=pasaje).update(created_at=momento(dia))
        return pasaje

    def crear_encomienda(self, viaje, dia: date, estado: str = "registrado", precio: str = "20.00") -> Encomienda:
        encomienda = Encomienda.objects.create(
            viaje=viaje, remitente_nombre="Luis Mamani", remitente_ci="1234567",
            destinatario_nombre="Rosa Choque", destinatario_ci="7654321", descripcion_contenido="Ropa",
            peso_kg=Decimal("4.00"), precio_envio=Decimal(precio), estado=estado, registrado_por=self.usuario,
        )
        Encomienda.objects.filter(pk=encomienda.pk).update(created_at=momento(dia))
        return encomienda
