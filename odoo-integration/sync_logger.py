# sync_logger.py — Logging dual: archivo rotativo + tabla SQLite
"""
Gestiona el registro de acciones de sincronización tanto en un archivo
de log rotativo como en la tabla odoo_sync_log de la BD del scraper.
"""

import os
import sys
import logging
import sqlite3
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

# Cargar .env
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Módulo de logging compartido con scraper-fabricacion (ver common/logging_utils.py).
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from common.logging_utils import setup_rotating_logger

# --- Configuración de logging ---
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_PATH = os.path.join(LOG_DIR, "odoo_sync.log")
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 3


def setup_sync_logger() -> logging.Logger:
    """Configura y retorna el logger para la sincronización con Odoo (ver common/logging_utils.py)."""
    return setup_rotating_logger(
        name="odoo_sync",
        log_path=LOG_PATH,
        max_bytes=LOG_MAX_BYTES,
        backup_count=LOG_BACKUP_COUNT,
        file_level=logging.DEBUG,
        console_level=logging.INFO,
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# --- Tabla de sincronización en la BD ---

def _get_db_path() -> str:
    """Obtiene la ruta a la base de datos del scraper."""
    env_path = os.getenv("DB_PATH", "").strip()
    if env_path:
        if not os.path.isabs(env_path):
            env_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), env_path
            )
        return os.path.normpath(env_path)
    return os.path.normpath(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "scraper-fabricacion", "data", "fabricacion.db"
        )
    )


def init_sync_table():
    """Crea la tabla odoo_sync_log si no existe."""
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS odoo_sync_log (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp           DATETIME,
                    proyecto_nombre     TEXT,
                    producto_nombre     TEXT,
                    odoo_model          TEXT,
                    odoo_id             INTEGER,
                    accion              TEXT,
                    detalle             TEXT
                )
            """)
    finally:
        conn.close()


def log_sync_action(
    proyecto_nombre: str,
    odoo_model: str,
    accion: str,
    odoo_id: Optional[int] = None,
    producto_nombre: Optional[str] = None,
    detalle: Optional[str] = None,
):
    """
    Registra una acción de sincronización en la tabla odoo_sync_log.

    Parámetros:
        proyecto_nombre: Nombre del proyecto en la BD local.
        odoo_model: Modelo de Odoo afectado ('project.project' o 'project.task').
        accion: Tipo de acción ('created', 'updated', 'skipped', 'error').
        odoo_id: ID del registro en Odoo (si aplica).
        producto_nombre: Nombre del producto (None si es el proyecto padre).
        detalle: Mensaje de error o descripción adicional.
    """
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO odoo_sync_log
                    (timestamp, proyecto_nombre, producto_nombre, odoo_model, odoo_id, accion, detalle)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                proyecto_nombre,
                producto_nombre,
                odoo_model,
                odoo_id,
                accion,
                detalle,
            ))
    finally:
        conn.close()
