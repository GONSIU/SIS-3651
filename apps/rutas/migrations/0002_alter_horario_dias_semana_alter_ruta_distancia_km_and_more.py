import apps.rutas.models
import django.core.validators
import django.db.models.functions.text
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rutas', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='horario',
            name='dias_semana',
            field=models.CharField(help_text='Ej. L,M,X,J,V,S,D', max_length=13, validators=[apps.rutas.models.validar_dias_semana]),
        ),
        migrations.AlterField(
            model_name='ruta',
            name='distancia_km',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))]),
        ),
        migrations.AlterField(
            model_name='ruta',
            name='duracion_minutos',
            field=models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AlterField(
            model_name='terminal',
            name='ciudad',
            field=models.CharField(max_length=50, validators=[django.core.validators.RegexValidator(code='solo_letras', message='Usa solo letras, separadas por un espacio.', regex='^[^\\W\\d_]+(?: [^\\W\\d_]+)*\\Z')]),
        ),
        migrations.AlterField(
            model_name='terminal',
            name='direccion',
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AlterField(
            model_name='terminal',
            name='nombre',
            field=models.CharField(max_length=50, validators=[django.core.validators.RegexValidator(code='solo_letras', message='Usa solo letras, separadas por un espacio.', regex='^[^\\W\\d_]+(?: [^\\W\\d_]+)*\\Z')]),
        ),
        migrations.AddConstraint(
            model_name='ruta',
            constraint=models.CheckConstraint(check=models.Q(('distancia_km__isnull', True), ('distancia_km__gt', 0), _connector='OR'), name='ruta_distancia_km_positiva', violation_error_message='La distancia debe ser mayor a 0.'),
        ),
        migrations.AddConstraint(
            model_name='ruta',
            constraint=models.CheckConstraint(check=models.Q(('duracion_minutos__isnull', True), ('duracion_minutos__gte', 1), _connector='OR'), name='ruta_duracion_minutos_positiva', violation_error_message='La duracion debe ser de al menos 1 minuto.'),
        ),
        migrations.AddConstraint(
            model_name='ruta',
            constraint=models.CheckConstraint(check=models.Q(('origen', models.F('destino')), _negated=True), name='ruta_origen_distinto_destino', violation_error_message='El destino debe ser distinto del origen.'),
        ),
        migrations.AddConstraint(
            model_name='ruta',
            constraint=models.UniqueConstraint(fields=('origen', 'destino'), name='uniq_ruta_origen_destino', violation_error_message='Ya existe una ruta con ese origen y destino.'),
        ),
        migrations.AddConstraint(
            model_name='terminal',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Lower('nombre'), django.db.models.functions.text.Lower('ciudad'), name='uniq_terminal_nombre_ciudad', violation_error_message='Ya existe un terminal con ese nombre en esa ciudad.'),
        ),
    ]
