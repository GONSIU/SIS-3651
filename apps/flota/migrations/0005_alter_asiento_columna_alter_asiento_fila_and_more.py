import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('flota', '0004_normalizar_placa_y_tipo'),
    ]

    operations = [
        migrations.AlterField(
            model_name='asiento',
            name='columna',
            field=models.PositiveSmallIntegerField(blank=True, help_text='1-4: ventana/pasillo por lado', null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(4)]),
        ),
        migrations.AlterField(
            model_name='asiento',
            name='fila',
            field=models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AlterField(
            model_name='asiento',
            name='piso',
            field=models.PositiveSmallIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)]),
        ),
        migrations.AlterField(
            model_name='bus',
            name='capacidad_carga_kg',
            field=models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='bus',
            name='capacidad_pasajeros',
            field=models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(80)]),
        ),
        migrations.AlterField(
            model_name='bus',
            name='nombre_tipo',
            field=models.CharField(choices=[('Leito', 'Leito'), ('Cama', 'Cama'), ('Semicama', 'Semicama')], max_length=20),
        ),
        migrations.AlterField(
            model_name='bus',
            name='placa',
            field=models.CharField(max_length=10, unique=True, validators=[django.core.validators.RegexValidator(code='placa_invalida', message='Ingresa una placa valida: 3 o 4 digitos y 3 letras (Ej. 1234ABC).', regex='^[0-9]{3,4}[A-Z]{3}\\Z')]),
        ),
        migrations.AddConstraint(
            model_name='asiento',
            constraint=models.CheckConstraint(check=models.Q(('fila__isnull', True), ('fila__gte', 1), _connector='OR'), name='asiento_fila_positiva', violation_error_message='La fila debe ser mayor o igual a 1.'),
        ),
        migrations.AddConstraint(
            model_name='asiento',
            constraint=models.CheckConstraint(check=models.Q(('columna__isnull', True), models.Q(('columna__gte', 1), ('columna__lte', 4)), _connector='OR'), name='asiento_columna_rango', violation_error_message='La columna debe estar entre 1 y 4.'),
        ),
        migrations.AddConstraint(
            model_name='asiento',
            constraint=models.CheckConstraint(check=models.Q(('piso__gte', 1)), name='asiento_piso_positivo', violation_error_message='El piso debe ser mayor o igual a 1.'),
        ),
        migrations.AddConstraint(
            model_name='bus',
            constraint=models.CheckConstraint(check=models.Q(('capacidad_pasajeros__gte', 1), ('capacidad_pasajeros__lte', 80)), name='bus_capacidad_pasajeros_rango', violation_error_message='La capacidad debe estar entre 1 y 80 pasajeros.'),
        ),
        migrations.AddConstraint(
            model_name='bus',
            constraint=models.CheckConstraint(check=models.Q(('capacidad_carga_kg__gte', 0)), name='bus_capacidad_carga_no_negativa', violation_error_message='La capacidad de carga no puede ser negativa.'),
        ),
    ]
