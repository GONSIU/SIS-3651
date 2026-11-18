from django.core.validators import RegexValidator

# NIT boliviano (solo digitos) o CI con complemento opcional: la factura se puede emitir
# a una empresa o a una persona.
validar_nit_o_ci = RegexValidator(
    regex=r"^[0-9]{5,15}(?:-[0-9A-Z]{2})?\Z",
    message="Ingresa un NIT o CI valido: de 5 a 15 digitos.",
    code="nit_invalido",
)
