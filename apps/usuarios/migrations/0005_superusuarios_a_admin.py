"""Ajuste unico: los superusuarios creados antes de UsuarioManager pasan a rol admin.

No es una regla permanente: desde 0004, createsuperuser ya asigna rol="admin".
"""

from django.db import migrations


def superusuarios_a_admin(apps, schema_editor):
    # Modelo historico: el estado del modelo en esta migracion, no el de models.py.
    Usuario = apps.get_model("usuarios", "Usuario")
    Usuario.objects.filter(is_superuser=True).exclude(rol="admin").update(rol="admin")


class Migration(migrations.Migration):

    dependencies = [
        ("usuarios", "0004_usuario_manager"),
    ]

    operations = [
        # Sin reversa real: no se guarda que rol tenia cada uno antes del ajuste.
        migrations.RunPython(superusuarios_a_admin, migrations.RunPython.noop),
    ]
