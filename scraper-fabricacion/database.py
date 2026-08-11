import sqlite3
import os
from datetime import datetime
from typing import Optional, Tuple
from models import Proyecto, Producto, ProductoItem, Material

def init_db(db_path: str) -> sqlite3.Connection:
    """Crea el directorio de la base de datos y todas las tablas si no existen."""
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Crear tablas
    with conn:
        # proyectos
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proyectos (
                nombre TEXT PRIMARY KEY,
                cliente TEXT,
                estado TEXT,
                fecha_primera_carga DATETIME,
                fecha_ultima_sync DATETIME
            )
        """)
        
        # proyecto_productos
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proyecto_productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_nombre TEXT REFERENCES proyectos(nombre) ON DELETE CASCADE,
                nombre TEXT,
                cantidad REAL,
                solicitud TEXT,
                entrega_fc TEXT,
                entrega TEXT,
                estado TEXT,
                fecha_primera_carga DATETIME,
                fecha_ultima_sync DATETIME,
                UNIQUE (proyecto_nombre, nombre)
            )
        """)
        
        # producto_items
        conn.execute("""
            CREATE TABLE IF NOT EXISTS producto_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER REFERENCES proyecto_productos(id) ON DELETE CASCADE,
                nombre TEXT,
                cantidad REAL,
                solicitud TEXT,
                entrega_fc TEXT,
                entrega TEXT,
                estado TEXT,
                fecha_primera_carga DATETIME,
                fecha_ultima_sync DATETIME,
                UNIQUE (producto_id, nombre)
            )
        """)
        
        # proyectos_historial_estados
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proyectos_historial_estados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_nombre TEXT,
                estado_anterior TEXT,
                estado_nuevo TEXT,
                fecha_cambio DATETIME
            )
        """)
        
        # productos_historial_estados
        conn.execute("""
            CREATE TABLE IF NOT EXISTS productos_historial_estados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_nombre TEXT,
                producto_nombre TEXT,
                estado_anterior TEXT,
                estado_nuevo TEXT,
                fecha_cambio DATETIME
            )
        """)
        
        # items_historial_estados
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items_historial_estados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                producto_id INTEGER,
                item_nombre TEXT,
                estado_anterior TEXT,
                estado_nuevo TEXT,
                fecha_cambio DATETIME
            )
        """)
        
        # materiales
        conn.execute("""
            CREATE TABLE IF NOT EXISTS materiales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_nombre TEXT REFERENCES proyectos(nombre) ON DELETE CASCADE,
                tipo TEXT,
                codigo_mp TEXT,
                descripcion TEXT,
                proveedor TEXT,
                cantidad REAL,
                desperdicio_12 REAL,
                validacion_diseno REAL,
                stock_chapa_barras REAL,
                comprar REAL,
                precio_sw REAL,
                precio_compra REAL,
                orden_compra TEXT,
                numero_factura TEXT,
                estado_compra TEXT,
                comentarios TEXT,
                fecha_primera_carga DATETIME,
                fecha_ultima_sync DATETIME,
                UNIQUE (proyecto_nombre, tipo, codigo_mp)
            )
        """)
        
        # materiales_historial_estados
        conn.execute("""
            CREATE TABLE IF NOT EXISTS materiales_historial_estados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_nombre TEXT,
                codigo_mp TEXT,
                tipo TEXT,
                estado_anterior TEXT,
                estado_nuevo TEXT,
                fecha_cambio DATETIME
            )
        """)

        # proyecto_producto_materiales
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proyecto_producto_materiales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_nombre TEXT REFERENCES proyectos(nombre) ON DELETE CASCADE,
                producto_nombre TEXT,
                tipo TEXT, -- 'item' | 'suministro'
                nombre TEXT, -- Nombre del material/posición/suministro
                codigo_mp TEXT,
                descripcion_material TEXT,
                l_p REAL,
                a REAL,
                c REAL, -- Cantidad
                fecha_ultima_sync DATETIME,
                UNIQUE (proyecto_nombre, producto_nombre, tipo, nombre, codigo_mp)
            )
        """)
        
        # ejecuciones
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ejecuciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_inicio DATETIME,
                timestamp_fin DATETIME,
                estado TEXT,
                proyectos_procesados INTEGER DEFAULT 0,
                materiales_procesados INTEGER DEFAULT 0,
                mensaje_error TEXT
            )
        """)
        
        # checkpoint
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoint (
                id INTEGER PRIMARY KEY,
                ejecucion_id INTEGER REFERENCES ejecuciones(id) ON DELETE CASCADE,
                ultimo_proyecto_procesado TEXT,
                timestamp DATETIME
            )
        """)
        
        # proyectos_errores — registro de proyectos que fallaron durante el scraping
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proyectos_errores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ejecucion_id INTEGER REFERENCES ejecuciones(id) ON DELETE CASCADE,
                proyecto_nombre TEXT,
                error_mensaje TEXT,
                fecha DATETIME
            )
        """)
        
    return conn

# --- GETTERS DE ESTADO ACTUAL ---

def get_estado_proyecto(conn: sqlite3.Connection, nombre: str) -> Optional[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT estado FROM proyectos WHERE nombre = ?", (nombre,))
    row = cursor.fetchone()
    return row[0] if row else None

def get_estado_producto(conn: sqlite3.Connection, proyecto_nombre: str, nombre: str) -> Optional[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT estado FROM proyecto_productos WHERE proyecto_nombre = ? AND nombre = ?", (proyecto_nombre, nombre))
    row = cursor.fetchone()
    return row[0] if row else None

def get_estado_item(conn: sqlite3.Connection, producto_id: int, nombre: str) -> Optional[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT estado FROM producto_items WHERE producto_id = ? AND nombre = ?", (producto_id, nombre))
    row = cursor.fetchone()
    return row[0] if row else None

def get_estado_material(conn: sqlite3.Connection, proyecto_nombre: str, tipo: str, codigo_mp: str) -> Optional[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT estado_compra FROM materiales WHERE proyecto_nombre = ? AND tipo = ? AND codigo_mp = ?", (proyecto_nombre, tipo, codigo_mp))
    row = cursor.fetchone()
    return row[0] if row else None

# --- REGISTROS DE HISTORIAL ---

def registrar_cambio_proyecto(conn: sqlite3.Connection, nombre: str, anterior: str, nuevo: str):
    conn.execute("""
        INSERT INTO proyectos_historial_estados (proyecto_nombre, estado_anterior, estado_nuevo, fecha_cambio)
        VALUES (?, ?, ?, ?)
    """, (nombre, anterior, nuevo, datetime.now().isoformat()))

def registrar_cambio_producto(conn: sqlite3.Connection, proyecto_nombre: str, producto_nombre: str, anterior: str, nuevo: str):
    conn.execute("""
        INSERT INTO productos_historial_estados (proyecto_nombre, producto_nombre, estado_anterior, estado_nuevo, fecha_cambio)
        VALUES (?, ?, ?, ?, ?)
    """, (proyecto_nombre, producto_nombre, anterior, nuevo, datetime.now().isoformat()))

def registrar_cambio_item(conn: sqlite3.Connection, producto_id: int, item_nombre: str, anterior: str, nuevo: str):
    conn.execute("""
        INSERT INTO items_historial_estados (producto_id, item_nombre, estado_anterior, estado_nuevo, fecha_cambio)
        VALUES (?, ?, ?, ?, ?)
    """, (producto_id, item_nombre, anterior, nuevo, datetime.now().isoformat()))

def registrar_cambio_material(conn: sqlite3.Connection, proyecto_nombre: str, codigo_mp: str, tipo: str, anterior: str, nuevo: str):
    conn.execute("""
        INSERT INTO materiales_historial_estados (proyecto_nombre, codigo_mp, tipo, estado_anterior, estado_nuevo, fecha_cambio)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (proyecto_nombre, codigo_mp, tipo, anterior, nuevo, datetime.now().isoformat()))

# --- UPSERTS ---

def upsert_proyecto(conn: sqlite3.Connection, proyecto: Proyecto):
    now = datetime.now().isoformat()
    estado_actual = get_estado_proyecto(conn, proyecto.nombre)
    
    with conn:
        if estado_actual is None:
            # Nuevo registro
            conn.execute("""
                INSERT INTO proyectos (nombre, cliente, estado, fecha_primera_carga, fecha_ultima_sync)
                VALUES (?, ?, ?, ?, ?)
            """, (proyecto.nombre, proyecto.cliente, proyecto.estado, now, now))
        else:
            # Ya existe
            if estado_actual != proyecto.estado:
                registrar_cambio_proyecto(conn, proyecto.nombre, estado_actual, proyecto.estado)
            conn.execute("""
                UPDATE proyectos SET cliente = ?, estado = ?, fecha_ultima_sync = ?
                WHERE nombre = ?
            """, (proyecto.cliente, proyecto.estado, now, proyecto.nombre))

def upsert_producto(conn: sqlite3.Connection, producto: Producto) -> int:
    now = datetime.now().isoformat()
    estado_actual = get_estado_producto(conn, producto.proyecto_nombre, producto.nombre)
    
    with conn:
        if estado_actual is None:
            # Nuevo registro
            cursor = conn.execute("""
                INSERT INTO proyecto_productos (
                    proyecto_nombre, nombre, cantidad, solicitud, entrega_fc, entrega, estado, fecha_primera_carga, fecha_ultima_sync
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                producto.proyecto_nombre, producto.nombre, producto.cantidad, producto.solicitud,
                producto.entrega_fc, producto.entrega, producto.estado, now, now
            ))
            return cursor.lastrowid
        else:
            # Ya existe
            if estado_actual != producto.estado:
                registrar_cambio_producto(conn, producto.proyecto_nombre, producto.nombre, estado_actual, producto.estado)
            conn.execute("""
                UPDATE proyecto_productos SET
                    cantidad = ?, solicitud = ?, entrega_fc = ?, entrega = ?, estado = ?, fecha_ultima_sync = ?
                WHERE proyecto_nombre = ? AND nombre = ?
            """, (
                producto.cantidad, producto.solicitud, producto.entrega_fc, producto.entrega, producto.estado, now,
                producto.proyecto_nombre, producto.nombre
            ))
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM proyecto_productos WHERE proyecto_nombre = ? AND nombre = ?", (producto.proyecto_nombre, producto.nombre))
            return cursor.fetchone()[0]

def upsert_item(conn: sqlite3.Connection, producto_id: int, item: ProductoItem):
    now = datetime.now().isoformat()
    estado_actual = get_estado_item(conn, producto_id, item.nombre)
    
    with conn:
        if estado_actual is None:
            # Nuevo registro
            conn.execute("""
                INSERT INTO producto_items (
                    producto_id, nombre, cantidad, solicitud, entrega_fc, entrega, estado, fecha_primera_carga, fecha_ultima_sync
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                producto_id, item.nombre, item.cantidad, item.solicitud,
                item.entrega_fc, item.entrega, item.estado, now, now
            ))
        else:
            # Ya existe
            if estado_actual != item.estado:
                registrar_cambio_item(conn, producto_id, item.nombre, estado_actual, item.estado)
            conn.execute("""
                UPDATE producto_items SET
                    cantidad = ?, solicitud = ?, entrega_fc = ?, entrega = ?, estado = ?, fecha_ultima_sync = ?
                WHERE producto_id = ? AND nombre = ?
            """, (
                item.cantidad, item.solicitud, item.entrega_fc, item.entrega, item.estado, now,
                producto_id, item.nombre
            ))

def upsert_material(conn: sqlite3.Connection, material: Material):
    now = datetime.now().isoformat()
    estado_actual = get_estado_material(conn, material.proyecto_nombre, material.tipo, material.codigo_mp)
    
    with conn:
        if estado_actual is None:
            # Nuevo registro
            conn.execute("""
                INSERT INTO materiales (
                    proyecto_nombre, tipo, codigo_mp, descripcion, proveedor, cantidad, desperdicio_12,
                    validacion_diseno, stock_chapa_barras, comprar, precio_sw, precio_compra, orden_compra,
                    numero_factura, estado_compra, comentarios, fecha_primera_carga, fecha_ultima_sync
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                material.proyecto_nombre, material.tipo, material.codigo_mp, material.descripcion,
                material.proveedor, material.cantidad, material.desperdicio_12, material.validacion_diseno,
                material.stock_chapa_barras, material.comprar, material.precio_sw, material.precio_compra,
                material.orden_compra, material.numero_factura, material.estado_compra, material.comentarios,
                now, now
            ))
        else:
            # Ya existe
            if estado_actual != material.estado_compra:
                registrar_cambio_material(conn, material.proyecto_nombre, material.codigo_mp, material.tipo, estado_actual, material.estado_compra)
            conn.execute("""
                UPDATE materiales SET
                    descripcion = ?, proveedor = ?, cantidad = ?, desperdicio_12 = ?, validacion_diseno = ?,
                    stock_chapa_barras = ?, comprar = ?, precio_sw = ?, precio_compra = ?, orden_compra = ?,
                    numero_factura = ?, estado_compra = ?, comentarios = ?, fecha_ultima_sync = ?
                WHERE proyecto_nombre = ? AND tipo = ? AND codigo_mp = ?
            """, (
                material.descripcion, material.proveedor, material.cantidad, material.desperdicio_12,
                material.validacion_diseno, material.stock_chapa_barras, material.comprar, material.precio_sw,
                material.precio_compra, material.orden_compra, material.numero_factura, material.estado_compra,
                material.comentarios, now, material.proyecto_nombre, material.tipo, material.codigo_mp
            ))

def upsert_producto_material(conn: sqlite3.Connection, mat_data: dict):
    now = datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM proyecto_producto_materiales 
        WHERE proyecto_nombre = ? AND producto_nombre = ? AND tipo = ? AND nombre = ? AND codigo_mp = ?
    """, (
        mat_data["proyecto_nombre"], mat_data["producto_nombre"], mat_data["tipo"],
        mat_data["nombre"], mat_data["codigo_mp"]
    ))
    row = cursor.fetchone()
    
    with conn:
        if row is None:
            conn.execute("""
                INSERT INTO proyecto_producto_materiales (
                    proyecto_nombre, producto_nombre, tipo, nombre, codigo_mp,
                    descripcion_material, l_p, a, c, fecha_ultima_sync
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mat_data["proyecto_nombre"], mat_data["producto_nombre"], mat_data["tipo"],
                mat_data["nombre"], mat_data["codigo_mp"], mat_data["descripcion_material"],
                mat_data["l_p"], mat_data["a"], mat_data["c"], now
            ))
        else:
            conn.execute("""
                UPDATE proyecto_producto_materiales SET
                    descripcion_material = ?, l_p = ?, a = ?, c = ?, fecha_ultima_sync = ?
                WHERE id = ?
            """, (
                mat_data["descripcion_material"], mat_data["l_p"], mat_data["a"],
                mat_data["c"], now, row[0]
            ))

# --- CONTROL DE EJECUCIONES Y CHECKPOINTS ---

def iniciar_ejecucion(conn: sqlite3.Connection) -> int:
    cursor = conn.cursor()
    with conn:
        cursor.execute("""
            INSERT INTO ejecuciones (timestamp_inicio, estado)
            VALUES (?, ?)
        """, (datetime.now().isoformat(), "parcial"))
        return cursor.lastrowid

def finalizar_ejecucion(conn: sqlite3.Connection, eid: int, estado: str, proyectos: int, materiales: int, error: Optional[str] = None):
    with conn:
        conn.execute("""
            UPDATE ejecuciones SET
                timestamp_fin = ?, estado = ?, proyectos_procesados = ?, materiales_procesados = ?, mensaje_error = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), estado, proyectos, materiales, error, eid))

def guardar_checkpoint(conn: sqlite3.Connection, eid: int, ultimo_proyecto: str):
    with conn:
        # Usamos id = 1 para asegurar que solo exista un checkpoint a la vez (1 fila activa)
        conn.execute("""
            INSERT OR REPLACE INTO checkpoint (id, ejecucion_id, ultimo_proyecto_procesado, timestamp)
            VALUES (1, ?, ?, ?)
        """, (eid, ultimo_proyecto, datetime.now().isoformat()))

def limpiar_checkpoint(conn: sqlite3.Connection):
    with conn:
        conn.execute("DELETE FROM checkpoint")

def obtener_checkpoint(conn: sqlite3.Connection) -> Optional[Tuple[int, str]]:
    cursor = conn.cursor()
    cursor.execute("SELECT ejecucion_id, ultimo_proyecto_procesado FROM checkpoint WHERE id = 1")
    row = cursor.fetchone()
    return row if row else None

def registrar_error_proyecto(conn: sqlite3.Connection, ejecucion_id: int, proyecto_nombre: str, error_mensaje: str):
    """Registra un proyecto que falló durante el scraping para análisis posterior."""
    with conn:
        conn.execute("""
            INSERT INTO proyectos_errores (ejecucion_id, proyecto_nombre, error_mensaje, fecha)
            VALUES (?, ?, ?, ?)
        """, (ejecucion_id, proyecto_nombre, error_mensaje, datetime.now().isoformat()))
