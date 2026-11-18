from django.core.management.base import BaseCommand

from apps.ventas.services import liberar_reservas_vencidas


class Command(BaseCommand):
    help = "Pasa a vencido las reservas cuyo plazo ya paso y libera sus asientos."

    def handle(self, *args, **options):
        cantidad = liberar_reservas_vencidas()
        self.stdout.write(self.style.SUCCESS(f"Reservas vencidas: {cantidad}."))
