"""
Script de exploración manual (NO es parte de un test suite automatizado).

⚠️ ADVERTENCIA: este script MODIFICA datos reales en la base de datos de
PRODUCCIÓN (fabricacion.db) para luego forzar una corrida del scraper y
verificar que el mecanismo de historial de cambios (`*_historial_estados`)
registra la transición correctamente. No hay entorno de staging: por eso
requiere una confirmación explícita antes de tocar nada.

Uso:
    python test_db_history.py --confirmar
    python test_db_history.py --confirmar --proyecto "NOMBRE_DEL_PROYECTO"

Sin --proyecto, se toma el proyecto sincronizado más recientemente de la BD
local (nunca un nombre hardcodeado: un nombre de ejemplo fijo en el código
queda desactualizado en cuanto el proyecto real deja de existir o se
renombra, y el UPDATE de más abajo falla en silencio — 0 filas afectadas,
sin ningún aviso — dejando parecer que el test pasó cuando en realidad no
tocó nada).

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


def elegir_proyecto_por_defecto(cursor: sqlite3.Cursor) -> str:
    """
    Elige un proyecto real de la BD local para la prueba, en vez de depender
    de un nombre hardcodeado en el código. Se toma el sincronizado más
    recientemente: es el que tiene más chances de seguir existiendo (y con
    datos vigentes) en el ERP en el momento en que se corre este script.
    """
    cursor.execute(
        "SELECT nombre FROM proyectos ORDER BY fecha_ultima_sync DESC LIMIT 1"
    )
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(
            "La tabla 'proyectos' está vacía. Corré el scraper al menos una "
            "vez antes de usar este script, o pasá un proyecto explícito con "
            "--proyecto."
        )
    return row[0]


def test_history(confirmar: bool, proyecto_nombre: str = None):
    if not os.path.exists(db_path):
        print(f"BD no encontrada en: {db_path}")
        print("Corré el scraper al menos una vez antes de usar este script.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if proyecto_nombre is None:
        try:
            proyecto_nombre = elegir_proyecto_por_defecto(cursor)
        except RuntimeError as e:
            print(f"Error: {e}")
            conn.close()
            return

    if not confirmar:
        print("Modo simulación (sin --confirmar): no se modifica nada.")
        print(f"  BD objetivo: {db_path}")
        print(f"  Proyecto que se modificaría temporalmente: '{proyecto_nombre}'")
        print("  Para ejecutar de verdad: python test_db_history.py --confirmar")
        conn.close()
        return

    # 1. Modificar estado del proyecto a uno ficticio.
    # Se valida rowcount para no quedar en falso positivo: si el proyecto no
    # existe (nombre mal escrito, o pasado a mano con --proyecto), el UPDATE
    # de sqlite no falla ni avisa por su cuenta — simplemente afecta 0 filas
    # y el resto del script seguiría de largo como si hubiera funcionado.
    print(f"Modificando estado de '{proyecto_nombre}' en la DB a 'Test Modificado'...")
    cursor.execute(
        "UPDATE proyectos SET estado = ? WHERE nombre = ?",
        ("Test Modificado", proyecto_nombre)
    )
    if cursor.rowcount == 0:
        print(
            f"Error: el UPDATE no afectó ninguna fila. El proyecto "
            f"'{proyecto_nombre}' no existe en la tabla 'proyectos'. Abortando "
            f"sin ejecutar el scraper (no tiene sentido lanzarlo para verificar "
            f"un cambio que nunca se aplicó)."
        )
        conn.rollback()
        conn.close()
        return
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
        if cursor.rowcount == 0:
            print(
                f"Advertencia: el UPDATE de producto no afectó ninguna fila "
                f"('{prod_nombre}' en '{proyecto_nombre}'). Se continúa igual: "
                f"la prueba del historial de proyecto ya quedó registrada arriba."
            )
            conn.rollback()
        else:
            conn.commit()
    else:
        print(f"'{proyecto_nombre}' no tiene productos cargados; se omite la prueba de historial de productos.")

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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--confirmar", action="store_true",
        help="Confirma que se quiere modificar datos reales de producción."
    )
    parser.add_argument(
        "--proyecto", default=None,
        help="Nombre exacto del proyecto a usar. Si se omite, se toma el "
             "sincronizado más recientemente de la BD local.",
    )
    args = parser.parse_args()
    test_history(confirmar=args.confirmar, proyecto_nombre=args.proyecto)
