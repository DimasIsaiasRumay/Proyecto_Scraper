# test_lectura_campos.py — Tests de _leer_valor_campo() y _material_field_id() (scraper-fabricacion/scraper.py)
"""
Fase 7 de docs/plan_fallback_formulario.md.

Estos tests no tocan el ERP ni abren un navegador real (mismo criterio que
el resto de la suite, ver conftest.py: "solo prueban funciones puras con
datos de ejemplo en memoria"). En vez de Playwright real se usan dobles
mínimos (_FakePage/_FakeLocator/_FakeElement) que implementan solo lo que
_leer_valor_campo() usa de verdad: count(), .first, evaluate(),
input_value(), inner_text().

Cubre el riesgo central de la Fase 3: antes del lector agnóstico,
inner_text() sobre un <input> devolvía "" en silencio (sin excepción), lo
que hubiera corrompido en la BD los campos que "Editar Formulario" muestra
como <input>/<select> en vez de <span> (verificado en vivo contra el ERP
real, ver Fase 2 del plan). Y el remapeo de IDs de MATERIAL_ID_OVERRIDES_FORMULARIO,
también verificado en vivo (Fase 2) y usado en la extracción real de
producción (Fase 6, corrida completa contra el ERP el 19/08/2026).
"""
import logging

from parsing import parse_float
from scraper import _leer_valor_campo, _material_field_id


class _FakeElement:
    """Doble mínimo de un elemento DOM, tal como lo consulta
    _leer_valor_campo(): tagName, inner_text(), input_value(), y el texto
    de la opción seleccionada de un <select> (vía evaluate())."""

    def __init__(self, tag, text="", value=None, selected_text=None):
        self.tag = tag
        self._text = text
        self._value = value
        self._selected_text = selected_text

    def inner_text(self):
        return self._text

    def input_value(self):
        return self._value

    def evaluate(self, script):
        if "tagName" in script:
            return self.tag
        if "selectedIndex" in script:
            return self._selected_text
        raise NotImplementedError(f"_FakeElement.evaluate no sabe responder: {script!r}")


class _FakeLocator:
    """Doble mínimo de playwright.sync_api.Locator. `.first` devuelve el
    mismo objeto (los selectores de estos tests resuelven a 0 o 1
    elemento, como en el uso real de _leer_valor_campo)."""

    def __init__(self, element=None):
        self._element = element

    def count(self):
        return 0 if self._element is None else 1

    @property
    def first(self):
        return self

    def evaluate(self, script):
        return self._element.evaluate(script)

    def input_value(self):
        return self._element.input_value()

    def inner_text(self):
        return self._element.inner_text()


class _FakePage:
    """Doble mínimo de playwright.sync_api.Page: resuelve page.locator(selector)
    contra un diccionario {selector: _FakeElement} armado a mano por test."""

    def __init__(self, elementos: dict):
        self._elementos = elementos

    def locator(self, selector):
        return _FakeLocator(self._elementos.get(selector))


class TestLeerValorCampo:
    def test_span_devuelve_inner_text(self):
        page = _FakePage({"#stock_13562": _FakeElement("SPAN", text="2")})
        assert _leer_valor_campo(page, "#stock_13562") == "2"

    def test_input_devuelve_input_value_no_inner_text(self):
        # El riesgo central de la Fase 3: un <input> con inner_text() vacío
        # (siempre lo está — un <input> no tiene texto visible entre tags)
        # pero con un value real no debe devolver "".
        page = _FakePage({"#stock_13562": _FakeElement("INPUT", text="", value="2")})
        assert _leer_valor_campo(page, "#stock_13562") == "2"

    def test_select_devuelve_texto_de_la_opcion_seleccionada(self):
        page = _FakePage({"#estado_compra_13562": _FakeElement("SELECT", selected_text="En Set IN")})
        assert _leer_valor_campo(page, "#estado_compra_13562") == "En Set IN"

    def test_textarea_se_trata_como_input(self):
        page = _FakePage({"#comentario_13562": _FakeElement("TEXTAREA", value="hola")})
        assert _leer_valor_campo(page, "#comentario_13562") == "hola"

    def test_recorta_espacios_en_los_extremos(self):
        page = _FakePage({"#stock_13562": _FakeElement("SPAN", text="  2  ")})
        assert _leer_valor_campo(page, "#stock_13562") == "2"

    def test_elemento_inexistente_devuelve_vacio_y_loguea_warning(self, caplog):
        page = _FakePage({})
        with caplog.at_level(logging.WARNING):
            resultado = _leer_valor_campo(page, "#no_existe_13562")
        assert resultado == ""
        assert "no resolvió ningún elemento" in caplog.text


class TestMaterialFieldIdVistaDetalle:
    def test_precio_sw_usa_id_de_detalle_por_default(self):
        assert _material_field_id("precio_sw", "13562", "item") == "#precio_actual_13562"

    def test_orden_compra_de_suministro_sin_prefijo_en_detalle(self):
        assert _material_field_id("orden_compra", "13566", "suministro", vista="detalle") == "#orden_compra_13566"


class TestMaterialFieldIdVistaFormulario:
    """Los 4 campos remapeados de docs/plan_fallback_formulario.md Fase 2/3,
    verificados en vivo contra el ERP real y contra la extracción end-to-end
    de la Fase 6 (corrida completa el 19/08/2026)."""

    def test_remapea_precio_sw_de_item(self):
        assert _material_field_id("precio_sw", "13562", "item", vista="formulario") == "#precio_sw_13562"

    def test_remapea_precio_sw_de_suministro(self):
        assert _material_field_id("precio_sw", "13566", "suministro", vista="formulario") == "#suministro_precio_sw_13566"

    def test_remapea_precio_compra_de_item(self):
        assert _material_field_id("precio_compra", "13562", "item", vista="formulario") == "#precio_comprado_13562"

    def test_remapea_precio_compra_de_suministro(self):
        assert _material_field_id("precio_compra", "13566", "suministro", vista="formulario") == "#suministro_precio_comprado_13566"

    def test_agrega_prefijo_a_orden_compra_de_suministro(self):
        # En Detalle este campo NO lleva prefijo incluso para suministros
        # (ver test_orden_compra_de_suministro_sin_prefijo_en_detalle) — es
        # justo la diferencia que hace falta remapear.
        assert _material_field_id("orden_compra", "13566", "suministro", vista="formulario") == "#suministro_orden_compra_13566"

    def test_agrega_prefijo_a_numero_factura_de_suministro(self):
        assert _material_field_id("numero_factura", "13566", "suministro", vista="formulario") == "#suministro_numero_factura_13566"

    def test_orden_compra_de_item_sigue_sin_prefijo_en_formulario(self):
        # El prefijo nuevo solo aplica a la variante de suministro (ver Fase 2
        # del plan) — para items, orden_compra/numero_factura no cambian.
        assert _material_field_id("orden_compra", "13562", "item", vista="formulario") == "#orden_compra_13562"

    def test_campo_sin_override_resuelve_igual_en_ambas_vistas(self):
        for vista in ("detalle", "formulario"):
            assert _material_field_id("cantidad", "13566", "suministro", vista=vista) == "#suministro_cant_13566"

    def test_override_es_por_campo_no_global(self):
        # "comprar" no está en MATERIAL_ID_OVERRIDES_FORMULARIO — confirma
        # que el remapeo no afecta campos que no lo necesitan.
        assert _material_field_id("comprar", "13562", "item", vista="formulario") == "#comprar_13562"


class TestParseFloatRegresion:
    def test_cadena_vacia_sigue_devolviendo_none(self):
        # Documenta el riesgo que _leer_valor_campo() evita antes de que el
        # valor llegue acá: si algún selector no resolviera, parse_float("")
        # sigue devolviendo None en silencio (comportamiento correcto de
        # parsing.py, sin cambios) — por eso la responsabilidad de avisar
        # recae en _leer_valor_campo(), que loguea warning explícito.
        assert parse_float("") is None
