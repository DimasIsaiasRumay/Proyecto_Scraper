# test_run_selection.py — Pruebas de selección de proyectos por corrida en database_reader.py
"""
Pruebas para get_ultima_ejecucion_valida, get_ejecucion_inicio y get_projects_desde.
Utiliza una base de datos SQLite temporal aislada en cada test.
"""

import sqlite3
import pytest
from typing import Optional

import database_reader as d
from odoo_models import ProyectoLocal


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Crea una base de datos temporal con las tablas ejecuciones y proyectos."""
    db_file = tmp_path / "test_fabricacion.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE ejecuciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_inicio TEXT,
            timestamp_fin TEXT,
            estado TEXT,
            proyectos_procesados INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE proyectos (
            nombre TEXT PRIMARY KEY,
            cliente TEXT,
            estado TEXT,
            fecha_primera_carga TEXT,
            fecha_ultima_sync TEXT,
            odoo_id INTEGER,
            odoo_location_id INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE proyecto_productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto_nombre TEXT,
            nombre TEXT,
            odoo_id INTEGER
        )
    """)
    conn.commit()
    conn.close()

    monkeypatch.setenv("DB_PATH", str(db_file.resolve()))
    return db_file


def _insert_ejecucion(db_path, inicio: str, fin: Optional[str], estado: str, procesados: int) -> int:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO ejecuciones (timestamp_inicio, timestamp_fin, estado, proyectos_procesados) VALUES (?, ?, ?, ?)",
        (inicio, fin, estado, procesados),
    )
    eid = cursor.lastrowid
    conn.commit()
    conn.close()
    return eid


def _insert_proyecto(
    db_path,
    nombre: str,
    cliente: Optional[str] = "Cliente Test",
    estado: Optional[str] = "Material OK",
    sync_date: Optional[str] = "2026-08-18T12:00:00.000000",
    odoo_id: Optional[int] = None,
    odoo_location_id: Optional[int] = None,
):
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO proyectos (nombre, cliente, estado, fecha_primera_carga, fecha_ultima_sync, odoo_id, odoo_location_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (nombre, cliente, estado, sync_date, sync_date, odoo_id, odoo_location_id),
    )
    conn.commit()
    conn.close()


class TestRunSelection:
    def test_elige_la_ultima_terminada_con_proyectos(self, temp_db):
        _insert_ejecucion(temp_db, "2026-08-18T10:00:00", "2026-08-18T10:10:00", "completado_con_errores", 10)
        _insert_ejecucion(temp_db, "2026-08-18T11:00:00", None, "en_progreso", 0)
        _insert_ejecucion(temp_db, "2026-08-18T12:00:00", "2026-08-18T12:15:00", "completado_con_errores", 25)

        valida = d.get_ultima_ejecucion_valida()
        assert valida is not None
        assert valida["id"] == 3
        assert valida["timestamp_inicio"] == "2026-08-18T12:00:00"

    def test_ignora_corrida_sin_timestamp_fin(self, temp_db):
        _insert_ejecucion(temp_db, "2026-08-18T11:00:00", None, "en_progreso", 0)
        assert d.get_ultima_ejecucion_valida() is None

    def test_ignora_corrida_con_cero_proyectos(self, temp_db):
        _insert_ejecucion(temp_db, "2026-08-18T11:00:00", "2026-08-18T11:05:00", "completado", 0)
        assert d.get_ultima_ejecucion_valida() is None

    def test_sin_corridas_devuelve_none(self, temp_db):
        assert d.get_ultima_ejecucion_valida() is None

    def test_get_ejecucion_inicio_sirve_para_corrida_abierta(self, temp_db):
        eid = _insert_ejecucion(temp_db, "2026-08-18T13:00:00.123456", None, "en_progreso", 5)
        inicio = d.get_ejecucion_inicio(eid)
        assert inicio == "2026-08-18T13:00:00.123456"

    def test_get_ejecucion_inicio_id_inexistente(self, temp_db):
        assert d.get_ejecucion_inicio(999) is None

    def test_get_projects_desde_filtra_por_fecha(self, temp_db):
        _insert_proyecto(temp_db, "OP_VIEJO", sync_date="2026-08-18T09:00:00")
        _insert_proyecto(temp_db, "OP_ACTUAL_1", sync_date="2026-08-18T11:05:00")
        _insert_proyecto(temp_db, "OP_ACTUAL_2", sync_date="2026-08-18T11:10:00")

        proyectos = d.get_projects_desde("2026-08-18T11:00:00")
        assert len(proyectos) == 2
        nombres = [p.nombre for p in proyectos]
        assert "OP_VIEJO" not in nombres
        assert "OP_ACTUAL_1" in nombres
        assert "OP_ACTUAL_2" in nombres

    def test_get_projects_desde_incluye_proyecto_que_fallo_despues(self, temp_db):
        _insert_proyecto(temp_db, "OP-ING-EPLIQ-070826-0001", sync_date="2026-08-18T11:30:00")
        proyectos = d.get_projects_desde("2026-08-18T11:29:06")
        assert len(proyectos) == 1
        assert proyectos[0].nombre == "OP-ING-EPLIQ-070826-0001"

    def test_get_projects_desde_ordena_por_nombre(self, temp_db):
        _insert_proyecto(temp_db, "Z_PROYECTO", sync_date="2026-08-18T12:00:00")
        _insert_proyecto(temp_db, "A_PROYECTO", sync_date="2026-08-18T12:00:00")
        _insert_proyecto(temp_db, "M_PROYECTO", sync_date="2026-08-18T12:00:00")

        proyectos = d.get_projects_desde("2026-08-18T11:00:00")
        nombres = [p.nombre for p in proyectos]
        assert nombres == ["A_PROYECTO", "M_PROYECTO", "Z_PROYECTO"]

    def test_get_projects_desde_trae_odoo_location_id(self, temp_db):
        _insert_proyecto(temp_db, "OP-CON-LOC", odoo_location_id=16, sync_date="2026-08-18T12:00:00")
        proyectos = d.get_projects_desde("2026-08-18T11:00:00")
        assert len(proyectos) == 1
        assert proyectos[0].odoo_location_id == 16
