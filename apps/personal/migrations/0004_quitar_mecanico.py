"""Quita el cargo "mecanico": no hay un rol de usuario que le corresponda.

Va antes de 0005, que cambia la CheckConstraint: una ficha que siga con "mecanico"
la haria fallar. 0002 y 0003 ya estaban aplicadas, por eso no se editan.
"""

from django.db import migrations


def mecanico_a_conductor(apps, schema_editor):
    Empleado = apps.get_model("personal", "Empleado")
    Empleado.objects.filter(cargo="mecanico").update(cargo="conductor")


class Migration(migrations.Migration):
    dependencies = [("personal", "0003_cargo_choices")]

    # Sin vuelta atras real: no se sabe que fichas eran de mecanico.
    operations = [migrations.RunPython(mecanico_a_conductor, migrations.RunPython.noop)]
