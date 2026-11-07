from django.core.validators import RegexValidator

validar_nombre_persona = RegexValidator(
    regex=r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*\Z",
    message="Ingresa un nombre valido",
    code="nombre_invalido",
)

validar_solo_letras = RegexValidator(
    regex=r"^[^\W\d_]+(?: [^\W\d_]+)*\Z",
    message="Usa solo letras",
    code="solo_letras",
)

validar_ci = RegexValidator(
    regex=r"^[0-9]{5,10}(?:-[0-9A-Z]{2})?\Z",
    message="Ingresa un CI valido: de 5 a 10 digitos.",
    code="ci_invalido",
)

validar_telefono = RegexValidator(
    regex=r"^\+?[0-9]{7,15}\Z",
    message="Ingresa un telefono valido",
    code="telefono_invalido",
)

validar_placa = RegexValidator(
    regex=r"^[0-9]{3,4}[A-Z]{3}\Z",
    message="Ingresa una placa valida (Ej. 1234ABC).",
    code="placa_invalida",
)


def normalizar_espacios(valor: str | None) -> str | None:
    if not valor:
        return valor
    return " ".join(valor.split())


def normalizar_ci(valor: str | None) -> str | None:
    if not valor:
        return valor
    return "".join(valor.split()).upper()


def normalizar_telefono(valor: str | None) -> str | None:
    if not valor:
        return valor
    return "".join(valor.split()).replace("-", "")


def normalizar_placa(valor: str | None) -> str | None:
    if not valor:
        return valor
    return "".join(valor.split()).replace("-", "").upper()
