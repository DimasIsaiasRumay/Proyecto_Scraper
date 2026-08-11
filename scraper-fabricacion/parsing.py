# parsing.py — Funciones puras de parseo de los valores crudos del ERP.
"""
Estas funciones vivían en scraper.py, que importa config.py al cargarse, y
config.py lee scraper-fabricacion/.env en tiempo de import (falla con
ConfigError si no existe). Eso hacía que los tests de parseo — que no tocan
ni el ERP ni el navegador — no se pudieran importar sin credenciales
presentes, y un error de colección abortaba la suite entera.

Acá no se importa config ni playwright: solo stdlib. Así los tests corren
en un clon limpio y en CI, sin .env ni navegador instalado.

scraper.py las re-exporta, así que el resto del código sigue haciendo
`from scraper import parse_date` sin cambios.
"""

import logging
from datetime import datetime
from typing import Optional

# Mismo logger que usa el scraper, para que las advertencias de parseo sigan
# apareciendo en scraper.log junto al resto de la traza de la corrida.
logger = logging.getLogger("scraper")


def parse_date(date_str: str) -> Optional[str]:
    """Convierte fechas formato argentino (DD-MM-YYYY) a ISO (YYYY-MM-DD).

    Si el valor no coincide con ningún formato conocido se loguea como
    advertencia y se devuelve None (nunca el string crudo), para que un
    valor no parseable no termine disfrazado de fecha ISO válida en la BD.
    """
    if not date_str:
        return None
    date_str = date_str.strip()
    if not date_str or date_str == "-" or date_str.lower() == "null" or date_str == "00-00-0000":
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    logger.warning(f"parse_date: no se pudo interpretar la fecha '{date_str}' con ningún formato conocido; se guarda como None.")
    return None


def parse_float(val_str: str) -> Optional[float]:
    """Normaliza y convierte strings con formato decimal (coma) a float.

    Si el valor no puede convertirse se loguea como advertencia y se
    devuelve None, para diferenciar "campo vacío en el ERP" de "no se pudo
    parsear" al revisar los logs.
    """
    if not val_str:
        return None
    original = val_str
    val_str = val_str.strip()
    if not val_str or val_str == "-" or val_str.lower() == "null":
        return None
    try:
        # Si tiene formato con comas decimales, normalizar (ej: 1.234,56 -> 1234.56 o 15,5 -> 15.5)
        if "," in val_str:
            val_str = val_str.replace(".", "").replace(",", ".")
        return float(val_str)
    except ValueError:
        logger.warning(f"parse_float: no se pudo convertir '{original}' a número; se guarda como None.")
        return None
