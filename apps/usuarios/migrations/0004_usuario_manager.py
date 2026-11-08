import apps.usuarios.models
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("usuarios", "0003_alter_usuario_ci_alter_usuario_first_name_and_more"),
    ]

    operations = [
        migrations.AlterModelManagers(
            name="usuario",
            managers=[
                ("objects", apps.usuarios.models.UsuarioManager()),
            ],
        ),
    ]
