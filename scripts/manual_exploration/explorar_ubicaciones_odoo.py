"""
Script de exploración manual (NO es parte del test suite automatizado).

Consulta en modo solo lectura el Odoo de PRODUCCIÓN para reconocer
la estructura de stock.location, ir.model.data y res.company.
No lo ejecuta pytest/CI: vive en scripts/manual_exploration/.
No imprime credenciales, URLs ni datos sensibles.
"""

import os
import sys
import json
import sqlite3

# Resolver paths relativos para importar módulos del proyecto
BASE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ODOO_DIR = os.path.join(BASE_DIR, "odoo-integration")
SCRAPER_DIR = os.path.join(BASE_DIR, "scraper-fabricacion")
sys.path.insert(0, ODOO_DIR)

from odoo_client import OdooClient


def sanitize_location_name(nombre: str) -> str:
    """Nombre apto para stock.location: '/' es separador de jerarquía en Odoo."""
    return nombre.strip().replace("/", "-")


def get_proyectos_corrida_39() -> list[str]:
    """Obtiene los 25 nombres de proyectos de la corrida 39 desde la BD local."""
    db_path = os.path.join(SCRAPER_DIR, "data", "fabricacion.db")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp_inicio FROM ejecuciones WHERE id = 39")
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("No se encontró la ejecución 39 en la base de datos local.")
        ts_inicio = row[0]
        cursor.execute(
            "SELECT nombre FROM proyectos WHERE fecha_ultima_sync >= ? ORDER BY nombre",
            (ts_inicio,)
        )
        return [r[0] for r in cursor.fetchall()]
    finally:
        conn.close()


def main():
    print("Iniciando exploración de stock.location en Odoo (modo solo lectura)...")
    print("Credenciales cargadas desde odoo-integration/.env (valores no mostrados).")

    client = OdooClient()

    # 1. Empresas
    print("\n--- 1. Empresas (res.company) ---")
    companies = client.search_read("res.company", [], ["id", "name"], limit=10)
    print(json.dumps(companies, indent=2, ensure_ascii=False))

    # 2. XML id del padre
    print("\n--- 2a. XML ID: stock.location_production ---")
    xml_id_1 = client.search_read(
        "ir.model.data",
        [["module", "=", "stock"], ["name", "=", "location_production"]],
        ["id", "module", "name", "model", "res_id"],
        limit=5
    )
    print(json.dumps(xml_id_1, indent=2, ensure_ascii=False))

    print("\n--- 2b. XML ID: stock.stock_location_production ---")
    xml_id_2 = client.search_read(
        "ir.model.data",
        [["module", "=", "stock"], ["name", "=", "stock_location_production"]],
        ["id", "module", "name", "model", "res_id"],
        limit=5
    )
    print(json.dumps(xml_id_2, indent=2, ensure_ascii=False))

    # 3. Padre por nombre (fallback)
    print("\n--- 3. Padre por nombre (name='Production', location_id=False) ---")
    parent_by_name = client.search_read(
        "stock.location",
        [["name", "=", "Production"], ["location_id", "=", False]],
        ["id", "name", "complete_name", "usage", "location_id", "company_id", "active"],
        limit=10
    )
    print(json.dumps(parent_by_name, indent=2, ensure_ascii=False))

    padre_id = parent_by_name[0]["id"] if parent_by_name else 12

    # 4. Todo lo que tenga usage=production (para ver la trampa)
    print("\n--- 4. Registros con usage='production' ---")
    all_production_usage = client.search_read(
        "stock.location",
        [["usage", "=", "production"]],
        ["id", "name", "complete_name", "usage", "location_id", "active"],
        limit=50
    )
    print(json.dumps(all_production_usage, indent=2, ensure_ascii=False))

    # 5. Hijos actuales del padre resuelto
    print(f"\n--- 5. Hijos actuales del padre resuelto (location_id={padre_id}) ---")
    children = client.search_read(
        "stock.location",
        [["location_id", "=", padre_id]],
        ["id", "name", "complete_name", "usage", "active"],
        limit=100
    )
    print(json.dumps(children, indent=2, ensure_ascii=False))

    # 6. Inventario completo, incluyendo archivadas
    print("\n--- 6. Inventario completo stock.location (activas e inactivas) ---")
    all_locations = client.search_read(
        "stock.location",
        [["active", "in", [True, False]]],
        ["id", "name", "complete_name", "usage", "location_id", "active"],
        limit=200
    )
    print(json.dumps(all_locations, indent=2, ensure_ascii=False))

    # 7. Choque de nombres: los 25 nombres de la corrida 39 ya saneados
    nombres_crudos = get_proyectos_corrida_39()
    nombres_saneados = [sanitize_location_name(n) for n in nombres_crudos]
    print(f"\n--- 7. Choque de nombres ({len(nombres_saneados)} proyectos de corrida 39) ---")
    matches = client.search_read(
        "stock.location",
        [["name", "in", nombres_saneados], ["active", "in", [True, False]]],
        ["id", "name", "complete_name", "location_id", "usage", "active"],
        limit=50
    )
    print(json.dumps(matches, indent=2, ensure_ascii=False))

    # 8. Metadatos de campos
    print("\n--- 8. Metadatos de campos (fields_get) ---")
    fields_info = client._call(
        "stock.location",
        "fields_get",
        {
            "allfields": ["name", "usage", "location_id", "company_id", "active", "complete_name"],
            "attributes": ["type", "required", "readonly", "store", "selection"],
        }
    )
    print(json.dumps(fields_info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
