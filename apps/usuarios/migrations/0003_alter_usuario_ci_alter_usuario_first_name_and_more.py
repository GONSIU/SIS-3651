import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0002_usuario_terminal_asignado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usuario',
            name='ci',
            field=models.CharField(blank=True, max_length=12, null=True, unique=True, validators=[django.core.validators.RegexValidator(code='ci_invalido', message='Ingresa un CI valido: de 5 a 10 digitos y complemento opcional (Ej. 1234567-1B).', regex='^[0-9]{5,10}(?:-[0-9A-Z]{2})?\\Z')]),
        ),
        migrations.AlterField(
            model_name='usuario',
            name='first_name',
            field=models.CharField(blank=True, max_length=50, validators=[django.core.validators.RegexValidator(code='nombre_invalido', message='Ingresa un nombre valido: solo letras, separadas por un espacio, apostrofe o guion.', regex="^[^\\W\\d_]+(?:[ '\\-][^\\W\\d_]+)*\\Z")], verbose_name='first name'),
        ),
        migrations.AlterField(
            model_name='usuario',
            name='last_name',
            field=models.CharField(blank=True, max_length=50, validators=[django.core.validators.RegexValidator(code='nombre_invalido', message='Ingresa un nombre valido: solo letras, separadas por un espacio, apostrofe o guion.', regex="^[^\\W\\d_]+(?:[ '\\-][^\\W\\d_]+)*\\Z")], verbose_name='last name'),
        ),
        migrations.AlterField(
            model_name='usuario',
            name='telefono',
            field=models.CharField(blank=True, max_length=15, validators=[django.core.validators.RegexValidator(code='telefono_invalido', message='Ingresa un telefono valido: de 7 a 15 digitos, con + inicial opcional.', regex='^\\+?[0-9]{7,15}\\Z')]),
        ),
    ]
