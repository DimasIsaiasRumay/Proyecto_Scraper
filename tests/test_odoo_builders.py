# test_odoo_builders.py — Tests de los modelos y armadores de payload
# del lado odoo-integration/ (models.py, sync_projects.py, sync_tasks.py).
"""
No hacen ninguna llamada HTTP a Odoo — solo prueban la construcción de los
objetos tipados a partir de filas de BD, y el armado de los diccionarios
'vals' que después se mandan a la API.
"""
import logging
from odoo_models import ProyectoLocal, ProductoLocal
from sync_projects import _build_odoo_vals
from sync_tasks import _build_task_vals


class TestProductoLocalFromRow:
    def test_fila_completa(self):
        row = {"nombre": "Chapa 1.5x3", "cantidad": 5.0, "solicitud": "2026-01-01",
               "entrega_fc": "2026-01-05", "entrega": "2026-01-10", "estado": "OK",
               "odoo_id": 42}
        p = ProductoLocal.from_row(row, proyecto_nombre="OP_TEST")
        assert p.nombre == "Chapa 1.5x3"
        assert p.odoo_id == 42
        assert p.proyecto_nombre == "OP_TEST"

    def test_sin_nombre_usa_placeholder_y_loguea(self, caplog):
        with caplog.at_level(logging.WARNING):
            p = ProductoLocal.from_row({"cantidad": 1.0}, proyecto_nombre="OP_TEST")
        assert p.nombre == "SIN_NOMBRE"
        assert "nombre" in caplog.text.lower()

    def test_campos_faltantes_quedan_none(self):
        p = ProductoLocal.from_row({"nombre": "X"}, proyecto_nombre="OP_TEST")
        assert p.cantidad is None
        assert p.odoo_id is None


class TestProyectoLocalFromRow:
    def test_fila_completa_con_productos(self):
        row = {
            "nombre": "OP_TEST_123", "cliente": "Cliente X", "estado": "Material OK",
            "odoo_id": 7,
            "productos": [{"nombre": "Prod A", "cantidad": 1.0}],
        }
        proyecto = ProyectoLocal.from_row(row)
        assert proyecto.nombre == "OP_TEST_123"
        assert len(proyecto.productos) == 1
        assert proyecto.productos[0].nombre == "Prod A"
        assert proyecto.productos[0].proyecto_nombre == "OP_TEST_123"

    def test_sin_nombre_lanza_valueerror(self):
        import pytest
        with pytest.raises(ValueError):
            ProyectoLocal.from_row({"cliente": "X"})

    def test_sin_productos_lista_vacia(self):
        proyecto = ProyectoLocal.from_row({"nombre": "OP_TEST"})
        assert proyecto.productos == []


class TestBuildOdooVals:
    def test_con_cliente_y_estado(self):
        proyecto = ProyectoLocal(nombre="OP_TEST", cliente="Cliente X", estado="Material OK")
        vals = _build_odoo_vals(proyecto)
        assert vals["name"] == "OP_TEST"
        assert "Cliente: Cliente X" in vals["description"]
        assert "Estado: Material OK" in vals["description"]

    def test_sin_cliente_ni_estado_no_arma_description(self):
        proyecto = ProyectoLocal(nombre="OP_TEST")
        vals = _build_odoo_vals(proyecto)
        assert vals["name"] == "OP_TEST"
        assert "description" not in vals


class TestBuildTaskVals:
    def test_con_todos_los_campos(self):
        producto = ProductoLocal(
            proyecto_nombre="OP_TEST", nombre="Prod A", cantidad=5.0,
            solicitud="2026-01-01", entrega_fc="2026-01-05", entrega="2026-01-10",
            estado="OK",
        )
        vals = _build_task_vals(producto, project_odoo_id=99)
        assert vals["name"] == "Prod A"
        assert vals["project_id"] == 99
        assert vals["date_deadline"] == "2026-01-10"
        assert "Estado: OK" in vals["description"]
        assert "Cantidad: 5.0" in vals["description"]

    def test_sin_entrega_no_arma_date_deadline(self):
        producto = ProductoLocal(proyecto_nombre="OP_TEST", nombre="Prod A")
        vals = _build_task_vals(producto, project_odoo_id=99)
        assert "date_deadline" not in vals
