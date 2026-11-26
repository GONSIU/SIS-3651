"""Crea datos de demostracion para usar el sistema en desarrollo.

    docker compose exec web python manage.py poblar_demo            # base vacia
    docker compose exec web python manage.py poblar_demo --limpiar  # borra todo antes

Simula dos semanas de historia y la semana siguiente:
- Viajes pasados: se venden asientos con el viaje "programado" y despues se registran la
  salida y la llegada con los metodos de Viaje, que deciden que pasajes quedan usados y
  cuales no_show (como en la operacion real).
- Viajes de hoy en adelante: las ventas pasan por services.registrar_venta() y las
  reservas online por services.registrar_reserva(), con todas sus validaciones.

Las fechas se calculan desde hoy y el azar usa una semilla fija: los mismos datos cada
vez. Solo corre con DEBUG=True: nunca en produccion.
"""

import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.models import Notificacion
from apps.encomiendas.models import ComprobanteEncomienda, Encomienda, PagoEncomienda
from apps.flota.models import Bus
from apps.incidencias.models import Incidencia
from apps.personal.models import Empleado
from apps.rutas.models import Horario, Ruta, Terminal
from apps.usuarios.models import Usuario
from apps.ventas import services
from apps.ventas.models import Comprobante, Pago, Pasaje
from apps.viajes.models import Viaje

# Solo para desarrollo: se imprime al terminar.
PASSWORD_DEMO = "Demo-Naser-2026"
SEMILLA = 2026
DIAS_PASADOS = 14
DIAS_FUTUROS = 7

TERMINALES = [
    ("Terminal de Buses", "La Paz"),
    ("Terminal Oruro", "Oruro"),
    ("Terminal Cochabamba", "Cochabamba"),
    ("Terminal de Buses", "Santa Cruz"),
    ("Terminal Potosi", "Potosi"),
    ("Terminal Sucre", "Sucre"),
]

# origen, destino, km, minutos, precio, [(hora, dias)]. Cada horario tiene una hora
# distinta: un bus o conductor no tiene dos viajes a la misma hora del mismo dia.
RUTAS = [
    ("La Paz", "Oruro", 230, 210, 40, [(time(7, 0), "L,M,X,J,V,S,D"), (time(15, 0), "L,M,X,J,V")]),
    ("Oruro", "La Paz", 230, 210, 40, [(time(8, 30), "L,M,X,J,V,S,D"), (time(18, 0), "V,S,D")]),
    ("La Paz", "Cochabamba", 380, 420, 80, [(time(21, 0), "L,M,X,J,V,S,D")]),
    ("Cochabamba", "La Paz", 380, 420, 80, [(time(21, 30), "L,M,X,J,V,S,D")]),
    ("Cochabamba", "Santa Cruz", 470, 600, 100, [(time(20, 0), "L,M,X,J,V,S,D")]),
    ("Santa Cruz", "Cochabamba", 470, 600, 100, [(time(19, 30), "L,X,V,D")]),
    ("La Paz", "Potosi", 540, 540, 90, [(time(20, 30), "M,J,S")]),
    ("Potosi", "Sucre", 160, 180, 35, [(time(10, 0), "L,M,X,J,V,S,D")]),
]

BUSES = [
    ("1234ABC", "Semicama", 40, 300, 1),
    ("2345BCD", "Semicama", 44, 300, 1),
    ("3456CDE", "Cama", 36, 250, 1),
    ("4567DEF", "Cama", 48, 350, 2),
    ("5678EFG", "Leito", 30, 200, 2),
    ("6789FGH", "Semicama", 40, 300, 1),
]


@dataclass(frozen=True)
class Persona:
    username: str
    nombre: str
    apellido: str
    ci: str
    rol: str
    ciudad_terminal: str | None = None


PERSONAL = [
    Persona("admin", "Carla", "Mendoza", "4012345", "admin"),
    Persona("supervisor", "Jorge", "Quispe", "4023456", "supervisor", "La Paz"),
    Persona("ventanilla_lp", "Maria", "Condori", "4034567", "ventanillero", "La Paz"),
    Persona("ventanilla_cb", "Luis", "Rojas", "4045678", "ventanillero", "Cochabamba"),
    Persona("conductor1", "Pedro", "Mamani", "4056789", "conductor"),
    Persona("conductor2", "Raul", "Choque", "4067890", "conductor"),
    Persona("conductor3", "Hugo", "Vargas", "4078901", "conductor"),
]
CLIENTES = [
    Persona("cliente1", "Ana", "Gutierrez", "5012345", "cliente"),
    Persona("cliente2", "Diego", "Flores", "5023456", "cliente"),
]

NOMBRES = ["Rosa", "Juan", "Elena", "Mario", "Lucia", "Carlos", "Sonia", "Victor", "Paola", "Ruben",
           "Gabriela", "Fernando", "Silvia", "Andres", "Patricia", "Oscar"]
APELLIDOS = ["Perez", "Lopez", "Torrez", "Aguilar", "Ramos", "Huanca", "Cruz", "Medina", "Ortiz",
             "Chavez", "Salazar", "Limachi", "Apaza", "Villca", "Ticona", "Calle"]
CONTENIDOS = ["Ropa", "Documentos", "Repuestos", "Libros", "Alimentos secos", "Artesanias",
              "Herramientas", "Medicamentos"]


class Command(BaseCommand):
    help = "Crea datos de demostracion (solo con DEBUG=True). --limpiar borra todo antes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpiar", action="store_true",
            help="Vacia la base de datos (flush) antes de crear los datos.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("poblar_demo solo corre con DEBUG=True (desarrollo).")
        if options["limpiar"]:
            call_command("flush", interactive=False, verbosity=0)
        elif Usuario.objects.exists():
            raise CommandError("La base ya tiene datos. Usa --limpiar para borrarlos antes.")

        self.azar = random.Random(SEMILLA)
        self.ahora = timezone.now()
        self.hoy = timezone.localdate()
        self.contador_ci = 6000000

        with transaction.atomic():
            self._crear_catalogos()
            self._crear_usuarios()
            self._crear_viajes()
            self._simular_pasado()
            self._vender_futuro()
            self._casos_de_alerta()
            self._crear_incidencias()

        self._resumen()

    # ---------- Catalogos ----------

    def _crear_catalogos(self) -> None:
        self.terminales = {
            ciudad: Terminal.objects.create(nombre=nombre, ciudad=ciudad) for nombre, ciudad in TERMINALES
        }
        self.horarios: list[Horario] = []
        for origen, destino, km, minutos, precio, horarios in RUTAS:
            ruta = Ruta.objects.create(
                origen=self.terminales[origen], destino=self.terminales[destino],
                distancia_km=Decimal(km), duracion_minutos=minutos, precio_base=Decimal(precio),
            )
            for hora, dias in horarios:
                # Un carril distinto por horario (1, 2, 3...): se imprime en el boleto.
                self.horarios.append(Horario.objects.create(
                    ruta=ruta, hora_salida=hora, dias_semana=dias, carril=len(self.horarios) + 1,
                ))
        self.buses = []
        for placa, tipo, capacidad, carga, pisos in BUSES:
            bus = Bus.objects.create(
                placa=placa, nombre_tipo=tipo, capacidad_pasajeros=capacidad,
                capacidad_carga_kg=Decimal(carga), pisos=pisos,
            )
            bus.crear_asientos()
            self.buses.append(bus)

    def _crear_usuarios(self) -> None:
        self.usuarios: dict[str, Usuario] = {}
        for persona in PERSONAL + CLIENTES:
            datos = {
                "first_name": persona.nombre, "last_name": persona.apellido, "ci": persona.ci,
                "email": f"{persona.username}@example.com", "rol": persona.rol,
                "telefono": f"7{persona.ci}",
                "terminal_asignado": self.terminales.get(persona.ciudad_terminal),
            }
            if persona.rol == "admin":
                # Superusuario: entra tambien a /admin.
                usuario = Usuario.objects.create_superuser(persona.username, password=PASSWORD_DEMO, **datos)
            else:
                usuario = Usuario.objects.create_user(persona.username, password=PASSWORD_DEMO, **datos)
            self.usuarios[persona.username] = usuario

        for persona in PERSONAL:
            usuario = self.usuarios[persona.username]
            Empleado.objects.create(
                usuario=usuario, cargo=Empleado.cargos_para_rol(persona.rol)[0],
                fecha_ingreso=self.hoy - timedelta(days=self.azar.randint(200, 1500)),
            )
        self.vendedores = [self.usuarios["ventanilla_lp"], self.usuarios["ventanilla_cb"], self.usuarios["supervisor"]]
        self.conductores = [self.usuarios[f"conductor{n}"].empleado for n in (1, 2, 3)]

    def _crear_viajes(self) -> None:
        """Un viaje por horario y por dia en que opera, desde hace DIAS_PASADOS dias."""
        self.viajes_pasados: list[Viaje] = []
        self.viajes_futuros: list[Viaje] = []
        admin = self.usuarios["admin"]
        for desfase in range(-DIAS_PASADOS, DIAS_FUTUROS):
            fecha = self.hoy + timedelta(days=desfase)
            del_dia = sorted((h for h in self.horarios if h.opera_el(fecha)), key=lambda h: h.hora_salida)
            for indice, horario in enumerate(del_dia):
                viaje = Viaje.objects.create(
                    ruta=horario.ruta, horario=horario, fecha_salida=fecha,
                    bus=self.buses[(indice + desfase) % len(self.buses)],
                    conductor=self.conductores[(indice + desfase) % len(self.conductores)],
                    creado_por=admin, actualizado_por=admin,
                )
                viaje.crear_asientos_desde_bus()
                (self.viajes_pasados if fecha < self.hoy else self.viajes_futuros).append(viaje)

    # ---------- Datos aleatorios ----------

    def _pasajero(self) -> services.DatosPasajero:
        self.contador_ci += self.azar.randint(1, 900)
        nombre = f"{self.azar.choice(NOMBRES)} {self.azar.choice(APELLIDOS)}"
        return services.DatosPasajero(nombre=nombre, ci=str(self.contador_ci))

    def _facturacion(self, pasajero: services.DatosPasajero) -> services.DatosFacturacion:
        if self.azar.random() < 0.3:
            return services.DatosFacturacion(nit=pasajero.ci, razon_social=pasajero.nombre.split()[-1].upper())
        return services.DatosFacturacion()

    def _pago(self, monto: Decimal, metodos=("efectivo", "efectivo", "qr", "transferencia")) -> services.DatosPago:
        """QR y transferencia exigen una referencia (validacion de Pago). La de QR tiene la
        forma que genera static/js/pago_qr.js."""
        metodo = self.azar.choice(metodos)
        if metodo == "qr":
            referencia = "QR-" + "".join(self.azar.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8))
        elif metodo == "transferencia":
            referencia = f"TRF{self.azar.randint(100000, 999999)}"
        else:
            referencia = ""
        return services.DatosPago(metodo=metodo, monto=monto, referencia=referencia)

    def _asientos_libres(self, viaje: Viaje, proporcion: float) -> list:
        libres = list(viaje.asientos_viaje.filter(estado="disponible").order_by("pk"))
        return self.azar.sample(libres, int(len(libres) * proporcion))

    def _momento(self, fecha, hora: time) -> datetime:
        return timezone.make_aware(datetime.combine(fecha, hora))

    # ---------- Historia ----------

    def _simular_pasado(self) -> None:
        for viaje in self.viajes_pasados:
            salida = viaje.salida_programada
            for asiento in self._asientos_libres(viaje, self.azar.uniform(0.45, 0.85)):
                pasajero = self._pasajero()
                vendedor = self.azar.choice(self.vendedores)
                vendido_en = salida - timedelta(hours=self.azar.randint(2, 96))
                # Directo y no por registrar_venta(): el servicio (con razon) no vende
                # viajes con fecha pasada. Las constraints de la base se aplican igual.
                pasaje = Pasaje.objects.create(
                    viaje=viaje, asiento_viaje=asiento, cliente_nombre=pasajero.nombre,
                    cliente_ci=pasajero.ci, vendido_por=vendedor, actualizado_por=vendedor,
                    canal="ventanilla", precio=viaje.ruta.precio_base,
                    abordo=self.azar.random() < 0.92,
                )
                pasaje.marcar_como_vendido()
                facturacion = self._facturacion(pasajero)
                pago = self._pago(pasaje.precio)
                Pago.objects.create(
                    pasaje=pasaje, metodo=pago.metodo, monto=pago.monto,
                    referencia_externa=pago.referencia, registrado_por=vendedor,
                )
                Comprobante.objects.create(
                    pasaje=pasaje, tipo="factura" if facturacion.es_factura else "recibo",
                    nit_cliente=facturacion.nit, razon_social_cliente=facturacion.razon_social,
                )
                # created_at es auto_now_add: se corrige despues para que los reportes
                # vean la venta en su dia real.
                Pasaje.objects.filter(pk=pasaje.pk).update(created_at=vendido_en)
                Pago.objects.filter(pasaje=pasaje).update(created_at=vendido_en)

            self._encomiendas_pasadas(viaje)
            retraso = timedelta(minutes=self.azar.choice([0, 0, 0, 5, 10, 25]))
            viaje.registrar_salida(viaje.conductor.usuario, momento=salida + retraso)
            duracion = timedelta(minutes=viaje.ruta.duracion_minutos + self.azar.randint(-15, 40))
            viaje.registrar_llegada(viaje.conductor.usuario, momento=salida + retraso + duracion)

    def _encomiendas_pasadas(self, viaje: Viaje) -> None:
        ayer = self.hoy - timedelta(days=1)
        for _ in range(self.azar.randint(0, 3)):
            encomienda = self._nueva_encomienda(viaje, directo=True)
            Encomienda.objects.filter(pk=encomienda.pk).update(
                created_at=viaje.salida_programada - timedelta(hours=self.azar.randint(2, 30))
            )
            encomienda.cambiar_estado("en_destino", self.usuarios["ventanilla_cb"])
            # Las de ayer quedan en destino (sin retirar): aparecen en la campana.
            if viaje.fecha_salida < ayer:
                encomienda.cambiar_estado("entregado", self.usuarios["ventanilla_cb"])

    def _nueva_encomienda(self, viaje: Viaje, directo: bool) -> Encomienda:
        remitente, destinatario = self._pasajero(), self._pasajero()
        encomienda = Encomienda(
            viaje=viaje, remitente_nombre=remitente.nombre, remitente_ci=remitente.ci,
            destinatario_nombre=destinatario.nombre, destinatario_ci=destinatario.ci,
            descripcion_contenido=self.azar.choice(CONTENIDOS),
            peso_kg=Decimal(self.azar.randint(1, 25)), fragil=self.azar.random() < 0.2,
            valor_declarado=Decimal(self.azar.choice([0, 100, 300, 800])),
            registrado_por=self.azar.choice(self.vendedores),
        )
        if not directo:
            # Viaje futuro: mismas reglas que el formulario (capacidad de carga, fecha).
            encomienda.full_clean()
        encomienda.save()
        pago = self._pago(encomienda.precio_envio, metodos=("efectivo", "qr"))
        PagoEncomienda.objects.create(
            encomienda=encomienda, metodo=pago.metodo, monto=pago.monto, referencia_externa=pago.referencia,
        )
        ComprobanteEncomienda.objects.create(encomienda=encomienda)
        return encomienda

    # ---------- Hoy en adelante ----------

    def _vender_futuro(self) -> None:
        for viaje in self.viajes_futuros:
            dias = (viaje.fecha_salida - self.hoy).days
            # Mas ocupacion cuanto mas cerca esta la salida.
            proporcion = max(0.1, 0.6 - dias * 0.08)
            for asiento in self._asientos_libres(viaje, proporcion):
                pasajero = self._pasajero()
                services.registrar_venta(
                    viaje=viaje, asiento_viaje_id=asiento.pk, pasajero=pasajero,
                    precio=viaje.ruta.precio_base,
                    pago=self._pago(viaje.ruta.precio_base),
                    vendido_por=self.azar.choice(self.vendedores),
                    facturacion=self._facturacion(pasajero),
                )
            for _ in range(self.azar.randint(0, 2)):
                self._nueva_encomienda(viaje, directo=False)

        # Reservas online de los clientes: anticipo parcial (quedan reservadas) o total.
        reservables = [v for v in self.viajes_futuros if services.viaje_reservable_online(v, self.ahora)]
        for username in ("cliente1", "cliente2"):
            cliente = self.usuarios[username]
            for viaje in self.azar.sample(reservables, min(3, len(reservables))):
                self._reservar(viaje, cliente, completo=self.azar.random() < 0.3)

    def _reservar(self, viaje: Viaje, cliente: Usuario, completo: bool) -> Pasaje | None:
        asiento = viaje.asientos_viaje.filter(estado="disponible").order_by("pk").first()
        if asiento is None:
            return None
        precio = viaje.ruta.precio_base
        monto = precio if completo else services.monto_minimo_anticipo(precio)
        try:
            return services.registrar_reserva(
                viaje=viaje, asiento_viaje_id=asiento.pk, comprador=cliente,
                pasajero=services.DatosPasajero(nombre=cliente.get_full_name(), ci=cliente.ci),
                pago=self._pago(monto, metodos=("qr", "transferencia")), ahora=self.ahora,
            )
        except ValidationError:
            # Limites por cuenta (p. ej. ya reservo en ese viaje): se omite esa reserva.
            return None

    def _casos_de_alerta(self) -> None:
        """Casos para probar la campana y las pantallas de control."""
        de_hoy = [v for v in self.viajes_futuros if v.fecha_salida == self.hoy]
        # Un viaje retrasado hoy.
        pendientes_hoy = [v for v in de_hoy if v.salida_programada > self.ahora]
        if pendientes_hoy:
            pendientes_hoy[0].marcar_retraso(20, self.usuarios["supervisor"])
        # Un viaje de manana sin conductor asignado.
        manana = [v for v in self.viajes_futuros if v.fecha_salida == self.hoy + timedelta(days=1)]
        if manana:
            Viaje.objects.filter(pk=manana[-1].pk).update(conductor=None)
        # Una reserva que vence hoy: viaje de hoy que aun acepta reservas online.
        for viaje in de_hoy:
            if services.viaje_reservable_online(viaje, self.ahora):
                self._reservar(viaje, self.usuarios["cliente1"], completo=False)
                break

    def _crear_incidencias(self) -> None:
        """Incidentes del personal y reclamos de los clientes en distintos estados. Los
        cambios de estado pasan por cambiar_estado(), que avisa a los clientes."""
        supervisor = self.usuarios["supervisor"]
        pasados = list(
            Viaje.objects.filter(pk__in=[v.pk for v in self.viajes_pasados], estado="completado")
            .select_related("horario")
            .order_by("fecha_salida", "horario__hora_salida")
        )
        operativas = [
            ("falla_mecanica", "Falla en el sistema de frenos", "El conductor reporto ruido al frenar en bajada.", "resuelta",
             "Se cambiaron las pastillas de freno en taller."),
            ("retraso", "Salida retrasada por neblina", "Neblina densa en la carretera; se espero 40 minutos.", "resuelta",
             "Se informo a los pasajeros y el viaje se completo sin novedad."),
            ("dano_unidad", "Ventana trizada en el asiento 12", "Se encontro la ventana trizada al limpiar el bus.", "en_revision", ""),
            ("otro", "Pasajero olvido una maleta", "Maleta azul encontrada en la bodega al llegar.", "abierta", ""),
        ]
        for indice, (categoria, titulo, descripcion, estado, resolucion) in enumerate(operativas):
            viaje = pasados[indice * 3 % len(pasados)] if pasados else None
            incidencia = Incidencia.objects.create(
                categoria=categoria, titulo=titulo, descripcion=descripcion, viaje=viaje,
                ocurrido_en=viaje.salida_programada + timedelta(hours=1) if viaje else self.ahora,
                reportado_por=supervisor,
            )
            self._avanzar(incidencia, estado, resolucion, supervisor)

        reclamos = [
            ("cliente1", "reclamo", "El bus salio con retraso", "Salimos 30 minutos tarde y nadie aviso.", 2, "resuelta",
             "Disculpa las molestias: reforzamos el aviso de retrasos por notificacion."),
            ("cliente2", "reclamo", "Aire acondicionado sin funcionar", "Hizo mucho calor durante todo el viaje.", 3, "abierta", ""),
            ("cliente1", "sugerencia", "Wifi a bordo", "Seria bueno tener wifi en los buses cama.", 5, "abierta", ""),
        ]
        for username, categoria, titulo, descripcion, calificacion, estado, resolucion in reclamos:
            cliente = self.usuarios[username]
            pasaje = Pasaje.objects.filter(cliente=cliente).order_by("viaje__fecha_salida").first()
            reclamo = Incidencia.objects.create(
                categoria=categoria, titulo=titulo, descripcion=descripcion, pasaje=pasaje,
                calificacion=calificacion, reportado_por=cliente,
            )
            self._avanzar(reclamo, estado, resolucion, supervisor)

    @staticmethod
    def _avanzar(incidencia: Incidencia, estado: str, resolucion: str, usuario: Usuario) -> None:
        if estado in ("en_revision", "resuelta"):
            incidencia.cambiar_estado("en_revision", usuario)
        if estado == "resuelta":
            incidencia.cambiar_estado("resuelta", usuario, resolucion)

    # ---------- Salida ----------

    def _resumen(self) -> None:
        conteos = {
            "Terminales": Terminal.objects.count(), "Rutas": Ruta.objects.count(),
            "Horarios": Horario.objects.count(), "Buses": Bus.objects.count(),
            "Viajes": Viaje.objects.count(), "Pasajes": Pasaje.objects.count(),
            "Reservas pendientes": Pasaje.objects.filter(estado="reservado").count(),
            "Encomiendas": Encomienda.objects.count(),
            "Incidencias y reclamos": Incidencia.objects.count(),
            "Notificaciones de clientes": Notificacion.objects.count(),
        }
        for nombre, cantidad in conteos.items():
            self.stdout.write(f"  {nombre}: {cantidad}")
        self.stdout.write(self.style.SUCCESS(f"\nDatos de demo creados. Contrasena de todos: {PASSWORD_DEMO}"))
        for persona in PERSONAL + CLIENTES:
            self.stdout.write(f"  {persona.username:<15} {persona.rol}")
