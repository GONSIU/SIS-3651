from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('flota', '0005_alter_asiento_columna_alter_asiento_fila_and_more'),
        ('rutas', '0002_alter_horario_dias_semana_alter_ruta_distancia_km_and_more'),
        ('viajes', '0003_alter_asientoviaje_options'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='viaje',
            constraint=models.CheckConstraint(check=models.Q(('minutos_retraso', 0), ('estado__in', ['retrasado', 'en_curso', 'completado']), _connector='OR'), name='viaje_retraso_segun_estado', violation_error_message='Solo un viaje retrasado, en curso o completado puede tener retraso.'),
        ),
    ]
