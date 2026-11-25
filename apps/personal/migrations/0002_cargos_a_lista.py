"""Convierte el cargo en texto libre a una clave de la lista de cargos.

Debe correr antes de 0003, que agrega la CheckConstraint: con valores sueltos como
"Cajera" la constraint fallaria. Las tablas de cargos se copian aqui (no se importan del
modelo) porque una migracion debe dar el mismo resultado aunque el modelo cambie despues.
"""

from django.db import migrations

CARGOS_POR_ROL = {
    "ventanillero": ("ventanillero", "encargado_encomiendas"),
    "supervisor": ("supervisor",),
    "admin": ("administrador",),
    "conductor": ("conductor", "ayudante_bus", "mecanico"),
}

# Textos que se escribian a mano y la clave que les corresponde.
SINONIMOS = {
    "ventanillero": "ventanillero",
    "ventanillera": "ventanillero",
    "cajero": "ventanillero",
    "cajera": "ventanillero",
    "supervisor": "supervisor",
    "supervisora": "supervisor",
    "jefe": "supervisor",
    "jefe de terminal": "supervisor",
    "administrador": "administrador",
    "administradora": "administrador",
    "admin": "administrador",
    "conductor": "conductor",
    "conductora": "conductor",
    "chofer": "conductor",
    "encargado de encomiendas": "encargado_encomiendas",
    "ayudante": "ayudante_bus",
    "ayudante de bus": "ayudante_bus",
    "mecanico": "mecanico",
}


def a_lista(apps, schema_editor):
    """Usa el sinonimo si es compatible con el rol; si no, el primer cargo del rol."""
    Empleado = apps.get_model("personal", "Empleado")
    for empleado in Empleado.objects.select_related("usuario"):
        permitidos = CARGOS_POR_ROL.get(empleado.usuario.rol, ("ventanillero",))
        candidato = SINONIMOS.get(" ".join(empleado.cargo.lower().split()))
        nuevo = candidato if candidato in permitidos else permitidos[0]
        if nuevo != empleado.cargo:
            empleado.cargo = nuevo
            empleado.save(update_fields=["cargo"])


class Migration(migrations.Migration):
    dependencies = [
        ("personal", "0001_initial"),
        ("usuarios", "0007_alter_usuario_rol"),
    ]

    # Sin vuelta atras real: el texto original se pierde. noop deja revertir el esquema.
    operations = [migrations.RunPython(a_lista, migrations.RunPython.noop)]
