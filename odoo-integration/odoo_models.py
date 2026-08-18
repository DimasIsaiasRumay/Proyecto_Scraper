# odoo_models.py — Modelos tipados para los datos leídos de la BD local del scraper.
# (Nombrado "odoo_models" y no "models" a propósito: scraper-fabricacion/ también
# tiene un models.py, y main.py agrega ambas carpetas a sys.path para poder
# importar odoo_sync directamente — un nombre de módulo duplicado ahí causaba
# que Python cacheara el módulo equivocado bajo el nombre "models" y rompiera
# el import en main.py. Ver commit/nota de esta corrección.)
"""
Antes sync_locations.py recibía `Dict` sueltos (leídos vía sqlite3.Row -> dict())
y accedía a los campos con `project["nombre"]`. Un typo en el nombre de un campo
ahí solo se detecta en producción, cuando esa línea se ejecuta y explota con
KeyError. Este dataclass hace explícitos los campos esperados: un typo se
detecta al construir el objeto (o antes, con un linter/IDE), no en medio de
una corrida de sincronización.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("odoo_sync")


@dataclass
class ProyectoLocal:
    """Un proyecto leído de la tabla proyectos."""
    nombre: str
    cliente: Optional[str] = None
    estado: Optional[str] = None
    odoo_id: Optional[int] = None
    odoo_location_id: Optional[int] = None

    @classmethod
    def from_row(cls, row: dict) -> "ProyectoLocal":
        nombre = row.get("nombre")
        if not nombre:
            logger.warning(f"Proyecto sin 'nombre' en la BD local (fila: {row!r}); se omite.")
            raise ValueError("Proyecto sin 'nombre' — no se puede sincronizar con Odoo.")
        return cls(
            nombre=nombre,
            cliente=row.get("cliente"),
            estado=row.get("estado"),
            odoo_id=row.get("odoo_id"),
            odoo_location_id=row.get("odoo_location_id"),
        )
