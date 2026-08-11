# sync_logger.py — Logging dual: archivo rotativo + tabla SQLite
"""
Gestiona el registro de acciones de sincronización tanto en un archivo
de log rotativo como en la tabla odoo_sync_log de la BD del scraper.
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional

# Módulo de logging compartido con scraper-fabricacion (ver common/logging_utils.py).
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from common.logging_utils import setup_rotating_logger

# Resolución de ruta y conexión a la BD del scraper: reutilizadas desde
# database_reader.py (que ya carga el .env y valida que el archivo exista)
# en vez de duplicarlas acá. Antes este archivo tenía su propia copia de
# _get_db_path(), que podía desincronizarse silenciosamente de la de
# database_reader.py si una de las dos cambiaba y la otra no.
from database_reader import connect_db

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

def init_sync_table():
    """
    Crea la tabla odoo_sync_log si no existe.

    Requiere que fabricacion.db ya exista (la crea el scraper en su primera
    corrida). No se crea acá: sqlite3.connect() crea el archivo en silencio
    si el directorio padre existe, lo que dejaría una fabricacion.db con
    *solo* la tabla odoo_sync_log y sin el resto del esquema — un error
    mucho más confuso más adelante ("no such table: proyectos") que este
    chequeo explícito. connect_db() (database_reader.py) ya valida esto
    antes de conectar.
    """
    conn = connect_db()
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
    conn = connect_db()
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
