import django.core.validators
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0002_comprobante_codigo_control'),
        ('viajes', '0004_viaje_viaje_retraso_segun_estado'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='pago',
            name='monto',
            field=models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))]),
        ),
        migrations.AlterField(
            model_name='pasaje',
            name='cliente_ci',
            field=models.CharField(blank=True, max_length=12, validators=[django.core.validators.RegexValidator(code='ci_invalido', message='Ingresa un CI valido: de 5 a 10 digitos y complemento opcional (Ej. 1234567-1B).', regex='^[0-9]{5,10}(?:-[0-9A-Z]{2})?\\Z')]),
        ),
        migrations.AlterField(
            model_name='pasaje',
            name='cliente_nombre',
            field=models.CharField(blank=True, max_length=100, validators=[django.core.validators.RegexValidator(code='nombre_invalido', message='Ingresa un nombre valido: solo letras, separadas por un espacio, apostrofe o guion.', regex="^[^\\W\\d_]+(?:[ '\\-][^\\W\\d_]+)*\\Z")]),
        ),
        migrations.AlterField(
            model_name='pasaje',
            name='precio',
            field=models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))]),
        ),
        migrations.AddConstraint(
            model_name='pago',
            constraint=models.CheckConstraint(check=models.Q(('monto__gt', 0)), name='pago_monto_positivo', violation_error_message='El monto debe ser mayor a 0.'),
        ),
        migrations.AddConstraint(
            model_name='pasaje',
            constraint=models.CheckConstraint(check=models.Q(('precio__gt', 0)), name='pasaje_precio_positivo', violation_error_message='El precio debe ser mayor a 0.'),
        ),
        migrations.AddConstraint(
            model_name='pasaje',
            constraint=models.CheckConstraint(check=models.Q(('cliente__isnull', False), models.Q(('cliente_nombre', ''), _negated=True), _connector='OR'), name='pasaje_con_cliente_o_nombre', violation_error_message='Indica el cliente o el nombre del pasajero.'),
        ),
    ]
