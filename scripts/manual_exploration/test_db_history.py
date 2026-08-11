"""
Script de exploración manual (NO es parte de un test suite automatizado).

⚠️ ADVERTENCIA: este script MODIFICA datos reales en la base de datos de
PRODUCCIÓN (fabricacion.db) para luego forzar una corrida del scraper y
verificar que el mecanismo de historial de cambios (`*_historial_estados`)
registra la transición correctamente. No hay entorno de staging: por eso
requiere una confirmación explícita antes de tocar nada.

Uso:
    python test_db_history.py --confirmar

Sin el flag --confirmar, el script solo imprime lo que haría y sale.
"""
import argparse
import sqlite3
import os
import sys
import subprocess

_SCRAPER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scraper-fabricacion")
)
db_path = os.path.join(_SCRAPER_DIR, "data", "fabricacion.db")
main_py_path = os.path.join(_SCRAPER_DIR, "main.py")


def test_history(confirmar: bool):
    proyecto_nombre = "OP_CLIENTE_A_BANDEJA SOLAR_0403260846"

    if not confirmar:
        print("Modo simulación (sin --confirmar): no se modifica nada.")
        print(f"  BD objetivo: {db_path}")
        print(f"  Proyecto que se modificaría temporalmente: '{proyecto_nombre}'")
        print("  Para ejecutar de verdad: python test_db_history.py --confirmar")
        return

    if not os.path.exists(db_path):
        print(f"BD no encontrada en: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Modificar estado del proyecto a uno ficticio
    print(f"Modificando estado de '{proyecto_nombre}' en la DB a 'Test Modificado'...")
    cursor.execute(
        "UPDATE proyectos SET estado = ? WHERE nombre = ?",
        ("Test Modificado", proyecto_nombre)
    )
    conn.commit()

    # También modificar un producto para probar el historial de productos
    cursor.execute("SELECT nombre, estado FROM proyecto_productos WHERE proyecto_nombre = ? LIMIT 1", (proyecto_nombre,))
    prod_row = cursor.fetchone()
    if prod_row:
        prod_nombre, prod_estado = prod_row
        print(f"Modificando estado del producto '{prod_nombre}' a 'Test Modificado'...")
        cursor.execute(
            "UPDATE proyecto_productos SET estado = ? WHERE proyecto_nombre = ? AND nombre = ?",
            ("Test Modificado", proyecto_nombre, prod_nombre)
        )
        conn.commit()

    # 2. Ejecutar de nuevo el scraper en modo test para que sobrescriba el
    # valor ficticio con el real y quede registrado el cambio en el historial.
    print("Ejecutando scraper para detectar cambios...")
    subprocess.run(
        [sys.executable, main_py_path, "--force", "--test"],
        check=False,
    )

    # 3. Comprobar registros de historial
    print("\nResultados del historial de cambios:")

    cursor.execute("SELECT * FROM proyectos_historial_estados")
    proj_history = cursor.fetchall()
    print(f"Historial Proyectos ({len(proj_history)}):")
    for r in proj_history:
        print(r)

    cursor.execute("SELECT * FROM productos_historial_estados")
    prod_history = cursor.fetchall()
    print(f"Historial Productos ({len(prod_history)}):")
    for r in prod_history:
        print(r)

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirmar", action="store_true",
        help="Confirma que se quiere modificar datos reales de producción."
    )
    args = parser.parse_args()
    test_history(confirmar=args.confirmar)
