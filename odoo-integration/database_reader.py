# database_reader.py — Lectura y escritura de datos en la BD SQLite del scraper
"""
Lee proyectos de fabricacion.db filtrados por corrida para enviarlos a Odoo.
También escribe de vuelta los odoo_location_id obtenidos tras la sincronización.
"""

import os
import sqlite3
from typing import Dict, List, Optional
from dotenv import load_dotenv

from odoo_models import ProyectoLocal

# Cargar .env para obtener DB_PATH
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "scraper-fabricacion", "data", "fabricacion.db"
)


def _get_db_path() -> str:
    """Obtiene la ruta a la base de datos desde .env o usa la ruta por defecto."""
    env_path = os.getenv("DB_PATH", "").strip()
    if env_path:
        # Si es relativa, resolverla desde el directorio de este archivo
        if not os.path.isabs(env_path):
            env_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), env_path
            )
        return os.path.normpath(env_path)
    return os.path.normpath(_DEFAULT_DB_PATH)


def _connect() -> sqlite3.Connection:
    """Abre una conexión a la BD SQLite."""
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"Base de datos no encontrada: {db_path}. "
            f"Verifica que el scraper haya ejecutado al menos una vez."
        )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Acceso por nombre de columna
    return conn


# --- Migración: agregar columnas odoo_id si no existen ---

def ensure_odoo_id_columns():
    """
    Agrega las columnas odoo_id y odoo_location_id a la tabla proyectos
    (y odoo_id a proyecto_productos) si aún no existen.
    Es seguro llamar múltiples veces (idempotente).
    No afecta al scraper ya que usa columnas explícitas en sus queries.
    """
    conn = _connect()
    try:
        cursor = conn.cursor()

        # Verificar si la columna ya existe en 'proyectos'
        cursor.execute("PRAGMA table_info(proyectos)")
        columns_proyectos = [row["name"] for row in cursor.fetchall()]
        if "odoo_id" not in columns_proyectos:
            conn.execute("ALTER TABLE proyectos ADD COLUMN odoo_id INTEGER")
        if "odoo_location_id" not in columns_proyectos:
            conn.execute("ALTER TABLE proyectos ADD COLUMN odoo_location_id INTEGER")

        # Verificar si la columna ya existe en 'proyecto_productos'
        cursor.execute("PRAGMA table_info(proyecto_productos)")
        columns_productos = [row["name"] for row in cursor.fetchall()]
        if "odoo_id" not in columns_productos:
            conn.execute("ALTER TABLE proyecto_productos ADD COLUMN odoo_id INTEGER")

        conn.commit()
    finally:
        conn.close()


# --- Selección de proyectos por corrida ---

def get_ultima_ejecucion_valida() -> Optional[Dict]:
    """Última corrida terminada y con proyectos procesados.
    Retorna {"id": int, "timestamp_inicio": str} o None si no hay ninguna."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp_inicio FROM ejecuciones
            WHERE timestamp_fin IS NOT NULL AND proyectos_procesados > 0
            ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return None
        return {"id": row["id"], "timestamp_inicio": row["timestamp_inicio"]}
    finally:
        conn.close()


def get_ejecucion_inicio(ejecucion_id: int) -> Optional[str]:
    """timestamp_inicio de una corrida puntual. None si el id no existe.
    Sin filtro de timestamp_fin para soportar corridas en progreso llamadas desde el bot."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp_inicio FROM ejecuciones WHERE id = ?", (ejecucion_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return row["timestamp_inicio"]
    finally:
        conn.close()


def get_projects_desde(timestamp_inicio: str) -> List[ProyectoLocal]:
    """Lee los proyectos modificados a partir de timestamp_inicio ordenados por nombre."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nombre, cliente, estado, odoo_id, odoo_location_id
            FROM proyectos
            WHERE fecha_ultima_sync >= ?
            ORDER BY nombre
        """, (timestamp_inicio,))
        rows = cursor.fetchall()
        resultado = []
        for row in rows:
            try:
                resultado.append(ProyectoLocal.from_row(dict(row)))
            except ValueError:
                continue
        return resultado
    finally:
        conn.close()


# --- Escritura de IDs ---

def save_project_odoo_id(proyecto_nombre: str, odoo_id: int):
    """Guarda el ID de Odoo (project.project histórico) para un proyecto en la BD local."""
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "UPDATE proyectos SET odoo_id = ? WHERE nombre = ?",
                (odoo_id, proyecto_nombre)
            )
    finally:
        conn.close()


def save_project_location_id(proyecto_nombre: str, location_id: int) -> None:
    """Guarda el ID de la ubicación de Odoo para un proyecto en la BD local."""
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "UPDATE proyectos SET odoo_location_id = ? WHERE nombre = ?",
                (location_id, proyecto_nombre)
            )
    finally:
        conn.close()


# --- Contadores ---

def get_project_count() -> int:
    """Retorna la cantidad total de proyectos en la BD."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM proyectos")
        return cursor.fetchone()[0]
    finally:
        conn.close()


# --- Alias públicos ---
# sync_logger.py necesita resolver la misma ruta de BD y abrir la conexión con
# el mismo chequeo de existencia (antes duplicaba _get_db_path() a mano, lo
# que permitía que las dos copias se desincronizaran). Se expone acá en vez de
# mover la lógica, para no reordenar el resto del archivo.
get_db_path = _get_db_path
connect_db = _connect
