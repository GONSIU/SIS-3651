from django.db import migrations

TIPOS = {"leito": "Leito", "cama": "Cama", "semicama": "Semicama"}


def normalizar_buses(apps, schema_editor):
    """Deja placas y tipos existentes en el formato que exigen las nuevas reglas."""
    Bus = apps.get_model("flota", "Bus")
    for bus in Bus.objects.all():
        bus.placa = "".join(bus.placa.split()).replace("-", "").upper()
        bus.nombre_tipo = TIPOS.get(bus.nombre_tipo.strip().lower(), bus.nombre_tipo)
        bus.save(update_fields=["placa", "nombre_tipo"])


class Migration(migrations.Migration):

    dependencies = [
        ("flota", "0003_alter_asiento_options_remove_bus_columnas_and_more"),
    ]

    operations = [
        migrations.RunPython(normalizar_buses, reverse_code=migrations.RunPython.noop),
    ]
