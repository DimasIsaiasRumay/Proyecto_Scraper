# logging_utils.py — Factory de logging compartida entre scraper-fabricacion
# y odoo-integration.
"""
Antes cada módulo definía su propio setup_logger()/setup_sync_logger() con
handlers, niveles y formatos ligeramente distintos (scraper.py: INFO en
archivo y consola; sync_logger.py: DEBUG en archivo, INFO en consola, otro
formato). Esta función unifica ambos en una sola política configurable,
para que agregar o cambiar el comportamiento de logging no requiera tocar
dos lugares.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_rotating_logger(
    name: str,
    log_path: str,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    file_level: int = logging.DEBUG,
    console_level: int = logging.INFO,
    fmt: str = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt: Optional[str] = None,
) -> logging.Logger:
    """
    Configura (o reutiliza, si ya tiene handlers) un logger con:
      - Archivo rotativo (nivel `file_level`, por defecto DEBUG: guarda más
        detalle en disco que lo que se muestra en consola).
      - Consola (nivel `console_level`, por defecto INFO).

    Ambos módulos del proyecto (scraper-fabricacion y odoo-integration)
    deben usar esta función en vez de definir su propio setup, para que el
    comportamiento de logging sea consistente en todo el sistema.
    """
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    logger = logging.getLogger(name)

    # Evitar duplicar handlers si se llama más de una vez (p. ej. al
    # importar el módulo repetidas veces en el mismo proceso).
    if logger.handlers:
        return logger

    logger.setLevel(min(file_level, console_level))

    formatter = logging.Formatter(fmt, datefmt=datefmt)

    file_handler = RotatingFileHandler(
        log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    # En Windows, la consola no siempre usa UTF-8 por defecto: los mensajes
    # de log con emoji (✅ ⚠️ ❌) pueden salir como mojibake o lanzar
    # UnicodeEncodeError. Si el stream lo soporta, se fuerza UTF-8 con
    # reemplazo de caracteres no representables en vez de romper el logging.
    try:
        console_handler.stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # stream sin reconfigure() (p. ej. no es un TextIOWrapper): se ignora.
    logger.addHandler(console_handler)

    return logger
