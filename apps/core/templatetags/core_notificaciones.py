"""Etiquetas del encabezado de base_dashboard.html: campana y barra de busqueda.

Es una etiqueta de inclusion y no un context processor: un context processor correria
en todas las paginas (tambien las publicas); asi las consultas solo se hacen donde se
muestra la campana."""

from django import template

from apps.core.notificaciones import ROLES_VENTANILLA, notificaciones_para

register = template.Library()


@register.inclusion_tag("core/_notificaciones.html", takes_context=True)
def campana_notificaciones(context):
    notificaciones = notificaciones_para(context["request"].user)
    return {
        "notificaciones": notificaciones,
        "total": sum(n.cantidad for n in notificaciones),
    }


@register.simple_tag
def puede_buscar(usuario) -> bool:
    """Los mismos roles que BuscarView: la barra no aparece para quien no puede usarla."""
    return getattr(usuario, "rol", None) in ROLES_VENTANILLA
