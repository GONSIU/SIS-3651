from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.flota.models import Bus
from apps.rutas.models import DIAS_VALIDOS, Horario, Ruta, Terminal
from apps.viajes.forms import ViajeForm
from apps.viajes.models import Viaje


class ViajeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        origen = Terminal.objects.create(nombre="Bimodal", ciudad="La Paz")
        destino = Terminal.objects.create(nombre="Central", ciudad="Oruro")
        cls.ruta = Ruta.objects.create(origen=origen, destino=destino)
        cls.otra_ruta = Ruta.objects.create(origen=destino, destino=origen)
        todos_los_dias = ",".join(DIAS_VALIDOS)
        cls.horario = Horario.objects.create(
            ruta=cls.ruta, hora_salida=time(8), dias_semana=todos_los_dias
        )
        cls.horario_misma_hora = Horario.objects.create(
            ruta=cls.otra_ruta, hora_salida=time(8), dias_semana=todos_los_dias
        )
        cls.bus = Bus.objects.create(
            placa="1234ABC", nombre_tipo="Semicama", capacidad_pasajeros=40, capacidad_carga_kg=0
        )
        cls.hoy = timezone.localdate()
        cls.manana = cls.hoy + timedelta(days=1)

    def viaje(self, **kwargs) -> Viaje:
        datos = {
            "ruta": self.ruta,
            "horario": self.horario,
            "bus": self.bus,
            "fecha_salida": self.manana,
        }
        return Viaje(**{**datos, **kwargs})

    def errores(self, viaje: Viaje) -> dict:
        with self.assertRaises(ValidationError) as error:
            viaje.full_clean()
        return error.exception.message_dict

    def test_viaje_valido(self):
        self.viaje().full_clean()
        self.viaje(fecha_salida=self.hoy).full_clean()

    def test_no_se_crea_en_fecha_pasada(self):
        viaje = self.viaje(fecha_salida=self.hoy - timedelta(days=1))
        self.assertIn("fecha_salida", self.errores(viaje))

    def test_viaje_historico_se_puede_editar(self):
        viaje = self.viaje(fecha_salida=self.hoy - timedelta(days=1))
        viaje.save()
        viaje.estado = "completado"
        viaje.full_clean()

    def test_horario_debe_ser_de_la_ruta(self):
        viaje = self.viaje(horario=self.horario_misma_hora)
        self.assertIn("horario", self.errores(viaje))

    def test_dia_debe_estar_en_el_horario(self):
        dia_siguiente = DIAS_VALIDOS[(self.manana.weekday() + 1) % 7]
        horario = Horario.objects.create(
            ruta=self.ruta, hora_salida=time(9), dias_semana=dia_siguiente
        )
        viaje = self.viaje(horario=horario)
        self.assertIn("fecha_salida", self.errores(viaje))

    def test_bus_inactivo_no_se_asigna_al_crear(self):
        for estado in ("mantenimiento", "fuera_servicio"):
            with self.subTest(estado=estado):
                bus = Bus(
                    placa="9999ZZZ", nombre_tipo="Cama", capacidad_pasajeros=30,
                    capacidad_carga_kg=0, estado=estado,
                )
                bus.save()
                self.assertIn("bus", self.errores(self.viaje(bus=bus)))
                bus.delete()

    def test_bus_que_pasa_a_mantenimiento_no_impide_editar_el_viaje(self):
        viaje = self.viaje()
        viaje.save()
        Bus.objects.filter(pk=self.bus.pk).update(estado="mantenimiento")
        viaje = Viaje.objects.get(pk=viaje.pk)
        viaje.full_clean()

    def test_cambiar_a_un_bus_inactivo_falla(self):
        viaje = self.viaje()
        viaje.save()
        inactivo = Bus.objects.create(
            placa="9999ZZZ", nombre_tipo="Cama", capacidad_pasajeros=30,
            capacidad_carga_kg=0, estado="mantenimiento",
        )
        viaje.bus = inactivo
        self.assertIn("bus", self.errores(viaje))

    def test_bus_no_puede_tener_dos_viajes_a_la_misma_hora(self):
        self.viaje().save()
        viaje = self.viaje(ruta=self.otra_ruta, horario=self.horario_misma_hora)
        self.assertIn("bus", self.errores(viaje))

    def test_viaje_cancelado_libera_el_bus(self):
        self.viaje(estado="cancelado").save()
        self.viaje(ruta=self.otra_ruta, horario=self.horario_misma_hora).full_clean()

    def test_otro_dia_no_es_conflicto(self):
        self.viaje().save()
        self.viaje(
            ruta=self.otra_ruta,
            horario=self.horario_misma_hora,
            fecha_salida=self.manana + timedelta(days=1),
        ).full_clean()

    def test_editar_un_viaje_no_choca_consigo_mismo(self):
        viaje = self.viaje()
        viaje.save()
        viaje.full_clean()

    def test_retraso_solo_en_estados_permitidos(self):
        for estado in ("retrasado", "en_curso", "completado"):
            with self.subTest(estado=estado):
                self.viaje(estado=estado, minutos_retraso=15).full_clean()
        for estado in ("programado", "cancelado"):
            with self.subTest(estado=estado):
                with self.assertRaises(ValidationError):
                    self.viaje(estado=estado, minutos_retraso=15).full_clean()
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.viaje(estado=estado, minutos_retraso=15).save()

    def test_formulario_muestra_el_error_en_el_campo(self):
        form = ViajeForm(
            data={
                "ruta": self.ruta.pk,
                "horario": self.horario_misma_hora.pk,
                "bus": self.bus.pk,
                "fecha_salida": self.manana.isoformat(),
                "estado": "programado",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("horario", form.errors)

    def test_formulario_con_campos_vacios_no_lanza_excepcion(self):
        form = ViajeForm(data={"estado": "programado"})
        self.assertFalse(form.is_valid())
        self.assertIn("ruta", form.errors)
