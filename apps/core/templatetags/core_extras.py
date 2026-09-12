from django import template

register = template.Library()


@register.filter
def moneda(valor):
    """Formatea un número como moneda: 150.5 -> 'Bs. 150.50'"""
    try:
        return f"Bs. {float(valor):,.2f}"
    except (TypeError, ValueError):
        return valor
