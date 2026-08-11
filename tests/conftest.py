# conftest.py — Configuración compartida de pytest para todo el proyecto.
"""
scraper-fabricacion/ y odoo-integration/ no son paquetes Python instalables
(son scripts sueltos ejecutados directamente con `python main.py` /
`python odoo_sync.py`), así que para poder importarlos desde los tests acá
se agregan sus rutas a sys.path antes de que corra cualquier test.

Estos tests NO tocan el ERP ni Odoo — solo prueban funciones puras
(parseo, validación, armado de payloads) con datos de ejemplo en memoria.
Para pruebas contra el ERP/Odoo reales, ver scripts/manual_exploration/.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_SCRAPER_DIR = os.path.join(_ROOT, "..", "scraper-fabricacion")
_ODOO_DIR = os.path.join(_ROOT, "..", "odoo-integration")

for path in (_SCRAPER_DIR, _ODOO_DIR):
    path = os.path.normpath(path)
    if path not in sys.path:
        sys.path.insert(0, path)
