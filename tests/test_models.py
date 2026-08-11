# test_models.py — Tests de validación de los dataclasses (scraper-fabricacion/models.py)
"""
Verifica que los __post_init__ de los modelos detecten datos raros
(nombres vacíos, tipos inesperados) y los logueen como advertencia, en vez
de fallar en silencio o dejarlos pasar sin ningún rastro.
"""
import logging
from models import Proyecto, Producto, ProductoItem, Material


class TestProductoItem:
    def test_construccion_normal_no_loguea_nada(self, caplog):
        with caplog.at_level(logging.WARNING):
            ProductoItem(nombre="Tornillo", cantidad=5.0, solicitud="2026-01-01",
                         entrega_fc="2026-01-05", entrega="2026-01-10", estado="OK")
        assert caplog.text == ""

    def test_nombre_vacio_loguea_advertencia(self, caplog):
        with caplog.at_level(logging.WARNING):
            ProductoItem(nombre="", cantidad=1.0, solicitud=None,
                         entrega_fc=None, entrega=None, estado="OK")
        assert "nombre" in caplog.text.lower()

    def test_cantidad_con_tipo_incorrecto_loguea_advertencia(self, caplog):
        with caplog.at_level(logging.WARNING):
            ProductoItem(nombre="Tornillo", cantidad="no-es-numero", solicitud=None,
                         entrega_fc=None, entrega=None, estado="OK")
        assert "cantidad" in caplog.text.lower()


class TestMaterial:
    def _material_base(self, **overrides):
        base = dict(
            proyecto_nombre="OP_TEST", tipo="item", codigo_mp="MP_001",
            descripcion="Chapa 1.5x3", proveedor="Proveedor SA", cantidad=1.0,
            desperdicio_12=0.1, validacion_diseno=0.0, stock_chapa_barras=0.0,
            comprar=1.0, precio_sw=100.0, precio_compra=90.0,
            orden_compra=None, numero_factura=None, estado_compra="Sin Controlar",
            comentarios=None,
        )
        base.update(overrides)
        return base

    def test_tipo_conocido_no_loguea_nada(self, caplog):
        with caplog.at_level(logging.WARNING):
            Material(**self._material_base(tipo="item"))
            Material(**self._material_base(tipo="suministro"))
        assert caplog.text == ""

    def test_tipo_desconocido_loguea_advertencia(self, caplog):
        with caplog.at_level(logging.WARNING):
            Material(**self._material_base(tipo="tipo_raro_no_esperado"))
        assert "tipo" in caplog.text.lower()

    def test_campo_numerico_con_tipo_incorrecto_loguea_advertencia(self, caplog):
        with caplog.at_level(logging.WARNING):
            Material(**self._material_base(precio_sw="no-es-numero"))
        assert "precio_sw" in caplog.text.lower()


class TestProyecto:
    def test_nombre_na_loguea_advertencia(self, caplog):
        with caplog.at_level(logging.WARNING):
            Proyecto(nombre="N/A", cliente="Cliente X", estado="Material OK")
        assert "nombre" in caplog.text.lower()

    def test_nombre_valido_no_loguea_nada(self, caplog):
        with caplog.at_level(logging.WARNING):
            Proyecto(nombre="OP_TEST_123", cliente="Cliente X", estado="Material OK")
        assert caplog.text == ""
