from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.core.validators import (
    normalizar_ci,
    normalizar_espacios,
    normalizar_placa,
    normalizar_telefono,
    validar_ci,
    validar_nombre_persona,
    validar_placa,
    validar_solo_letras,
    validar_telefono,
)


class ValidadoresRegexTests(SimpleTestCase):
    casos = [
        (
            validar_nombre_persona,
            ["Jose Maria", "Perez-Rojas", "D'Arcy", "José", "Muñoz", "Ñandú Peña"],
            ["as12", "ana--x", "123123", "Ana  Maria", "", "Ana\n", " Ana"],
        ),
        (
            validar_solo_letras,
            ["Santa Cruz", "Leito", "La Paz", "Cochabamba", "Potosí"],
            ["Terminal 2", "CB-1", "Santa  Cruz", "", "Oruro\n"],
        ),
        (
            validar_ci,
            ["12345", "1234567", "1234567890", "1234567-1B"],
            ["3ury237udbsn", "12", "1234", "12345678901", "1234567-1", "1234567-1b", "", "1234567\n"],
        ),
        (
            validar_telefono,
            ["+59171234567", "71234567", "1234567", "123456789012345"],
            ["7123-4567", "abc", "123456", "1234567890123456", "++59171234567", "", "71234567\n"],
        ),
        (
            validar_placa,
            ["1234ABC", "123ABC"],
            ["1234-abc", "1234abc", "12ABC", "12345ABC", "1234AB", "1234ÑBC", "", "1234ABC\n"],
        ),
    ]

    def test_valores_validos(self):
        for validador, validos, _ in self.casos:
            for valor in validos:
                with self.subTest(validador=validador.code, valor=valor):
                    validador(valor)

    def test_valores_invalidos(self):
        for validador, _, invalidos in self.casos:
            for valor in invalidos:
                with self.subTest(validador=validador.code, valor=valor):
                    with self.assertRaises(ValidationError):
                        validador(valor)


class NormalizadoresTests(SimpleTestCase):
    def test_normalizadores(self):
        casos = [
            (normalizar_espacios, "  Ana   Maria ", "Ana Maria"),
            (normalizar_ci, " 123 4567-1b", "1234567-1B"),
            (normalizar_telefono, "+591 712-34567", "+59171234567"),
            (normalizar_placa, "1234-abc", "1234ABC"),
            (normalizar_placa, " 1234 abc ", "1234ABC"),
        ]
        for funcion, entrada, esperado in casos:
            with self.subTest(funcion=funcion.__name__, entrada=entrada):
                self.assertEqual(funcion(entrada), esperado)

    def test_conservan_valores_vacios(self):
        for funcion in (normalizar_espacios, normalizar_ci, normalizar_telefono, normalizar_placa):
            with self.subTest(funcion=funcion.__name__):
                self.assertIsNone(funcion(None))
                self.assertEqual(funcion(""), "")
