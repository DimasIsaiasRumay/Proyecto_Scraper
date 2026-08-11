# database_reader.py — Lectura y escritura de odoo_id en la BD SQLite del scraper
"""
Lee proyectos y productos de fabricacion.db para enviarlos a Odoo.
También escribe de vuelta los odoo_id obtenidos tras la sincronización.
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
    Agrega las columnas odoo_id a las tablas proyectos y proyecto_productos
    si aún no existen. Es seguro llamar múltiples veces (idempotente).
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

        # Verificar si la columna ya existe en 'proyecto_productos'
        cursor.execute("PRAGMA table_info(proyecto_productos)")
        columns_productos = [row["name"] for row in cursor.fetchall()]
        if "odoo_id" not in columns_productos:
            conn.execute("ALTER TABLE proyecto_productos ADD COLUMN odoo_id INTEGER")

        conn.commit()
    finally:
        conn.close()


# --- Lectura ---

def get_all_projects() -> List[Dict]:
    """
    Lee todos los proyectos de la tabla 'proyectos'.
    Retorna una lista de dicts con claves: nombre, cliente, estado, odoo_id.
    """
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nombre, cliente, estado, fecha_primera_carga, fecha_ultima_sync, odoo_id
            FROM proyectos
            ORDER BY nombre
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_productos(proyecto_nombre: str) -> List[Dict]:
    """
    Lee todos los productos de un proyecto específico.
    Retorna una lista de dicts con claves: nombre, cantidad, solicitud,
    entrega_fc, entrega, estado, odoo_id.
    """
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT nombre, cantidad, solicitud, entrega_fc, entrega, estado, odoo_id
            FROM proyecto_productos
            WHERE proyecto_nombre = ?
            ORDER BY nombre
        """, (proyecto_nombre,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_all_projects_with_productos() -> List[Dict]:
    """
    Lee todos los proyectos junto con sus productos.
    Retorna una lista de dicts donde cada proyecto incluye una clave 'productos'
    con la lista de sus productos. Se mantiene el formato dict (no ProyectoLocal)
    para no romper el resumen/conteo de odoo_sync.py que itera sobre esto antes
    de tipar cada proyecto individualmente con get_all_projects_typed().
    """
    projects = get_all_projects()
    for project in projects:
        project["productos"] = get_productos(project["nombre"])
    return projects


def get_all_projects_typed() -> List[ProyectoLocal]:
    """
    Igual que get_all_projects_with_productos(), pero devuelve objetos
    ProyectoLocal/ProductoLocal tipados en vez de dicts sueltos — así un
    typo en un nombre de campo se detecta al construir el objeto, no
    recién cuando sync_projects.py/sync_tasks.py intentan leerlo.
    """
    proyectos_dict = get_all_projects_with_productos()
    resultado = []
    for p in proyectos_dict:
        try:
            resultado.append(ProyectoLocal.from_row(p))
        except ValueError:
            continue  # proyecto sin nombre; ya se logueó en ProyectoLocal.from_row
    return resultado


# --- Escritura de odoo_id ---

def save_project_odoo_id(proyecto_nombre: str, odoo_id: int):
    """Guarda el ID de Odoo para un proyecto en la BD local."""
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "UPDATE proyectos SET odoo_id = ? WHERE nombre = ?",
                (odoo_id, proyecto_nombre)
            )
    finally:
        conn.close()


def save_producto_odoo_id(proyecto_nombre: str, producto_nombre: str, odoo_id: int):
    """Guarda el ID de Odoo para un producto en la BD local."""
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "UPDATE proyecto_productos SET odoo_id = ? WHERE proyecto_nombre = ? AND nombre = ?",
                (odoo_id, proyecto_nombre, producto_nombre)
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


def get_producto_count() -> int:
    """Retorna la cantidad total de productos en la BD."""
    conn = _connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM proyecto_productos")
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
