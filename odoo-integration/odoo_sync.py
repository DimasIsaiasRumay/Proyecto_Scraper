# odoo_sync.py — Orquestador principal de sincronización con Odoo
"""
Punto de entrada para la sincronización de datos locales hacia Odoo.
Lee proyectos y productos de la BD SQLite y los crea/actualiza en Odoo
vía la API JSON-2.

Uso:
    python odoo_sync.py                     # sincroniza proyectos + tareas
    python odoo_sync.py --dry-run           # muestra qué haría sin tocar Odoo
    python odoo_sync.py --only-projects     # solo proyectos, sin tareas
    python odoo_sync.py --dry-run --only-projects
"""

import argparse
import sys
import time
from datetime import datetime

from odoo_client import OdooClient, OdooClientError
from database_reader import get_all_projects_typed, get_project_count, get_producto_count, ensure_odoo_id_columns
from sync_projects import sync_one_project, get_project_odoo_id
from sync_tasks import sync_one_task
from sync_logger import setup_sync_logger, init_sync_table

logger = setup_sync_logger()


def run_sync(dry_run: bool = False, only_projects: bool = False):
    """
    Ejecuta la sincronización completa.

    Parámetros:
        dry_run: Si True, solo muestra qué haría sin modificar Odoo.
        only_projects: Si True, solo sincroniza proyectos (sin tareas/productos).
    """
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    logger.info("=" * 70)
    logger.info(f"INICIO DE SINCRONIZACIÓN CON ODOO — {timestamp}")
    if dry_run:
        logger.info("⚠️  MODO DRY-RUN: No se realizarán cambios en Odoo")
    if only_projects:
        logger.info("ℹ️  MODO SOLO PROYECTOS: No se sincronizarán tareas/productos")
    logger.info("=" * 70)

    # 1. Inicializar tabla de log en la BD y migrar columnas odoo_id
    try:
        init_sync_table()
        ensure_odoo_id_columns()
    except Exception as e:
        logger.error(f"No se pudo inicializar la BD: {e}")
        # Continuamos igualmente, el log de archivo seguirá funcionando

    # 2. Conectar con Odoo
    try:
        client = OdooClient(allow_unconfigured=dry_run)
        logger.info(f"📡 Conectando a Odoo ({client.url or 'N/A'})...")

        if not dry_run:
            if client.test_connection():
                logger.info("✅ Conexión con Odoo verificada exitosamente.")
            else:
                logger.error("❌ No se pudo conectar con Odoo. Verifica las credenciales en .env")
                sys.exit(1)
        else:
            logger.info("📡 [DRY-RUN] Se omite la verificación de conexión con Odoo.")

    except OdooClientError as e:
        logger.error(f"❌ Error de configuración de Odoo: {e}")
        sys.exit(1)

    # 3. Leer datos de la BD local
    logger.info("📂 Leyendo datos de la base de datos local...")
    try:
        total_projects = get_project_count()
        total_productos = get_producto_count()
        logger.info(f"   BD local: {total_projects} proyectos, {total_productos} productos")

        projects = get_all_projects_typed()
    except Exception as e:
        logger.error(f"❌ Error leyendo la base de datos local: {e}")
        sys.exit(1)

    if not projects:
        logger.warning("⚠️  No hay proyectos en la BD local para sincronizar.")
        return

    # 4. Contadores de resultados
    stats = {
        "projects_created": 0,
        "projects_updated": 0,
        "projects_skipped": 0,
        "projects_error": 0,
        "tasks_created": 0,
        "tasks_updated": 0,
        "tasks_skipped": 0,
        "tasks_error": 0,
    }

    # 5. Sincronización proyecto por proyecto
    logger.info(f"\n🔄 Procesando {len(projects)} proyectos...")

    for i, project in enumerate(projects, 1):
        nombre = project.nombre
        productos = project.productos

        logger.info(f"\n[{i}/{len(projects)}] Proyecto: '{nombre}' ({len(productos)} productos)")

        # 5a. Sincronizar el proyecto
        odoo_id, accion = sync_one_project(client, project, dry_run=dry_run)
        stats[f"projects_{accion}"] = stats.get(f"projects_{accion}", 0) + 1

        # 5b. Sincronizar las tareas (productos) si corresponde
        if not only_projects and productos:
            # Obtener el ID del proyecto en Odoo (podría haberse creado recién)
            if odoo_id is None and not dry_run:
                odoo_id = get_project_odoo_id(client, nombre)

            if odoo_id is None and not dry_run:
                logger.warning(
                    f"  ⚠️  No se encontró el proyecto '{nombre}' en Odoo. "
                    f"Saltando {len(productos)} productos."
                )
                stats["tasks_skipped"] += len(productos)
                continue

            for producto in productos:
                if dry_run:
                    # En dry-run usamos un ID ficticio
                    _, task_accion = sync_one_task(
                        client, producto, 0, nombre, dry_run=True
                    )
                else:
                    _, task_accion = sync_one_task(
                        client, producto, odoo_id, nombre, dry_run=False
                    )
                stats[f"tasks_{task_accion}"] = stats.get(f"tasks_{task_accion}", 0) + 1

    # 6. Resumen final
    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 70)
    logger.info("RESUMEN DE SINCRONIZACIÓN")
    logger.info("=" * 70)
    logger.info(f"  Duración: {elapsed:.1f} segundos")
    logger.info(f"  Proyectos — Creados: {stats['projects_created']}, "
                f"Actualizados: {stats['projects_updated']}, "
                f"Saltados: {stats['projects_skipped']}, "
                f"Errores: {stats['projects_error']}")
    if not only_projects:
        logger.info(f"  Tareas    — Creadas: {stats['tasks_created']}, "
                    f"Actualizadas: {stats['tasks_updated']}, "
                    f"Saltadas: {stats['tasks_skipped']}, "
                    f"Errores: {stats['tasks_error']}")
    logger.info("=" * 70)

    # Retornar código de salida según errores
    total_errors = stats["projects_error"] + stats["tasks_error"]
    if total_errors > 0:
        logger.warning(f"⚠️  La sincronización terminó con {total_errors} error(es).")
        return 1
    else:
        logger.info("✅ Sincronización completada sin errores.")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Sincronización de proyectos con Odoo vía API JSON-2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python odoo_sync.py                     Sincroniza todo (proyectos + tareas)
  python odoo_sync.py --dry-run           Muestra qué haría sin tocar Odoo
  python odoo_sync.py --only-projects     Solo sincroniza proyectos
  python odoo_sync.py --dry-run --only-projects
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula la sincronización sin hacer cambios en Odoo.",
    )
    parser.add_argument(
        "--only-projects",
        action="store_true",
        help="Sincroniza solo los proyectos, sin crear tareas para los productos.",
    )
    args = parser.parse_args()

    exit_code = run_sync(dry_run=args.dry_run, only_projects=args.only_projects)
    sys.exit(exit_code or 0)


if __name__ == "__main__":
    main()
