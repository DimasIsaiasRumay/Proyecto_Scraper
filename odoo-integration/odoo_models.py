# odoo_models.py — Modelos tipados para los datos leídos de la BD local del scraper.
# (Nombrado "odoo_models" y no "models" a propósito: scraper-fabricacion/ también
# tiene un models.py, y main.py agrega ambas carpetas a sys.path para poder
# importar odoo_sync directamente — un nombre de módulo duplicado ahí causaba
# que Python cacheara el módulo equivocado bajo el nombre "models" y rompiera
# el import en main.py. Ver commit/nota de esta corrección.)
"""
Antes sync_projects.py y sync_tasks.py recibían `Dict` sueltos (leídos vía
sqlite3.Row -> dict()) y accedían a los campos con `project["nombre"]` o
`producto.get("cantidad")`. Un typo en el nombre de un campo ahí solo se
detecta en producción, cuando esa línea se ejecuta y explota con KeyError
(o, peor, con .get() devuelve None en silencio y el dato faltante ni se
nota). Estos dataclasses hacen explícitos los campos esperados: un typo se
detecta al construir el objeto (o antes, con un linter/IDE), no en medio de
una corrida de sincronización.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("odoo_sync")


@dataclass
class ProductoLocal:
    """Un producto (Nivel 2) leído de la tabla proyecto_productos."""
    proyecto_nombre: str
    nombre: str
    cantidad: Optional[float] = None
    solicitud: Optional[str] = None
    entrega_fc: Optional[str] = None
    entrega: Optional[str] = None
    estado: Optional[str] = None
    odoo_id: Optional[int] = None

    @classmethod
    def from_row(cls, row: dict, proyecto_nombre: str) -> "ProductoLocal":
        """Construye un ProductoLocal desde un dict de sqlite3.Row, logueando
        si falta el campo obligatorio 'nombre' en vez de fallar más abajo
        con un KeyError críptico."""
        nombre = row.get("nombre")
        if not nombre:
            logger.warning(
                f"Producto sin 'nombre' en proyecto '{proyecto_nombre}' "
                f"(fila de BD: {row!r}); se usa 'SIN_NOMBRE' como placeholder."
            )
            nombre = "SIN_NOMBRE"
        return cls(
            proyecto_nombre=proyecto_nombre,
            nombre=nombre,
            cantidad=row.get("cantidad"),
            solicitud=row.get("solicitud"),
            entrega_fc=row.get("entrega_fc"),
            entrega=row.get("entrega"),
            estado=row.get("estado"),
            odoo_id=row.get("odoo_id"),
        )


@dataclass
class ProyectoLocal:
    """Un proyecto leído de la tabla proyectos, con sus productos asociados."""
    nombre: str
    cliente: Optional[str] = None
    estado: Optional[str] = None
    odoo_id: Optional[int] = None
    productos: List[ProductoLocal] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: dict) -> "ProyectoLocal":
        nombre = row.get("nombre")
        if not nombre:
            logger.warning(f"Proyecto sin 'nombre' en la BD local (fila: {row!r}); se omite.")
            raise ValueError("Proyecto sin 'nombre' — no se puede sincronizar con Odoo.")
        productos_raw = row.get("productos", [])
        return cls(
            nombre=nombre,
            cliente=row.get("cliente"),
            estado=row.get("estado"),
            odoo_id=row.get("odoo_id"),
            productos=[ProductoLocal.from_row(p, nombre) for p in productos_raw],
        )
