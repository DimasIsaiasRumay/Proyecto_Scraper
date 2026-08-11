# test_parsing.py — Tests unitarios de parse_date() y parse_float()
"""
Corren en milisegundos, sin login ni navegador — pensados para detectar si
un cambio futuro rompe el parseo de fechas/números ANTES de que llegue a
tocar datos reales del ERP.

Se importan desde parsing.py y no desde scraper.py a propósito: scraper.py
importa config.py, que lee scraper-fabricacion/.env en tiempo de import y
falla con ConfigError si no existe. Importar desde acá dejaba la suite
entera sin correr en un clon limpio o en CI (error de colección, no un
simple fallo de test). parsing.py solo depende de la stdlib.
"""
import pytest
from parsing import parse_date, parse_float


class TestParseDate:
    def test_formato_argentino_guion(self):
        assert parse_date("31-12-2026") == "2026-12-31"

    def test_formato_argentino_barra(self):
        assert parse_date("31/12/2026") == "2026-12-31"

    def test_formato_iso_guion(self):
        assert parse_date("2026-12-31") == "2026-12-31"

    def test_formato_iso_barra(self):
        assert parse_date("2026/12/31") == "2026-12-31"

    def test_vacio_devuelve_none(self):
        assert parse_date("") is None
        assert parse_date(None) is None

    def test_guion_solo_devuelve_none(self):
        assert parse_date("-") is None

    def test_null_case_insensitive_devuelve_none(self):
        assert parse_date("null") is None
        assert parse_date("NULL") is None

    def test_fecha_cero_devuelve_none(self):
        assert parse_date("00-00-0000") is None

    def test_fecha_invalida_devuelve_none_no_el_string_crudo(self):
        # Antes del fix, esto devolvía el string sin parsear ("31-13-2026"),
        # quedando disfrazado de fecha ISO válida en la BD. Ahora debe ser None.
        assert parse_date("31-13-2026") is None
        assert parse_date("no es una fecha") is None

    def test_con_espacios_alrededor(self):
        assert parse_date("  31-12-2026  ") == "2026-12-31"


class TestParseFloat:
    def test_entero_simple(self):
        assert parse_float("15") == 15.0

    def test_decimal_con_punto(self):
        assert parse_float("15.5") == 15.5

    def test_decimal_con_coma_formato_argentino(self):
        assert parse_float("15,5") == 15.5

    def test_miles_y_decimales_formato_argentino(self):
        # 1.234,56 (formato AR: punto = miles, coma = decimal) -> 1234.56
        assert parse_float("1.234,56") == 1234.56

    def test_vacio_devuelve_none(self):
        assert parse_float("") is None
        assert parse_float(None) is None

    def test_guion_solo_devuelve_none(self):
        assert parse_float("-") is None

    def test_null_case_insensitive_devuelve_none(self):
        assert parse_float("null") is None

    def test_valor_no_numerico_devuelve_none(self):
        assert parse_float("no es un numero") is None

    def test_con_espacios_alrededor(self):
        assert parse_float("  15,5  ") == 15.5

    def test_cero(self):
        assert parse_float("0") == 0.0
        assert parse_float("0,0") == 0.0
