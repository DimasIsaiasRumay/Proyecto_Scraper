# odoo_sync.py — Orquestador principal de sincronización con Odoo
"""
Punto de entrada para la sincronización de datos locales hacia Odoo 19.0.
Lee proyectos de la última corrida del scraper (o una puntual con --ejecucion-id)
y crea las ubicaciones virtuales de producción en stock.location bajo 'Production'.

Uso:
    python odoo_sync.py                      # última corrida válida
    python odoo_sync.py --dry-run            # simulación real (solo lecturas)
    python odoo_sync.py --limit 1            # smoke test contra un solo proyecto
    python odoo_sync.py --ejecucion-id 39    # corrida puntual
"""

import argparse
import sys
import time
from datetime import datetime
from typing import Optional

from odoo_client import OdooClient, OdooClientError
from database_reader import (
    ensure_odoo_id_columns,
    get_ejecucion_inicio,
    get_project_count,
    get_projects_desde,
    get_ultima_ejecucion_valida,
)
from sync_locations import resolve_production_location, sync_one_location
from sync_logger import init_sync_table, setup_sync_logger

logger = setup_sync_logger()


def run_sync(
    dry_run: bool = False,
    only_projects: bool = False,
    ejecucion_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> int:
    """
    Ejecuta la sincronización de ubicaciones de producción con Odoo.

    Parámetros:
        dry_run: Si True, realiza solo consultas de lectura sin modificar Odoo ni la BD local.
        only_projects: Conservado por compatibilidad (no-op; ya no se crean tareas).
        ejecucion_id: ID de una corrida puntual. Si es None, usa la última corrida válida terminada.
        limit: Cantidad máxima de proyectos a procesar (ordenados por nombre).

    Retorna:
        0: Sincronización exitosa sin errores
        1: Error fatal (credenciales, BD, sin corrida válida, Production no resuelto)
        2: Completado con errores por proyecto
    """
    start_time = time.time()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    logger.info("=" * 70)
    logger.info(f"INICIO DE SINCRONIZACIÓN CON ODOO — {timestamp}")
    if dry_run:
        logger.info("⚠️  MODO DRY-RUN: No se realizarán cambios en Odoo ni en la BD local")
    if only_projects:
        logger.info("ℹ️  --only-projects ya no tiene efecto (no se crean tareas).")
    logger.info("=" * 70)

    # 1. Verificar que la BD del scraper exista, inicializar la tabla de log
    #    y asegurar existencia de columnas odoo_id / odoo_location_id.
    try:
        init_sync_table()
        ensure_odoo_id_columns()
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        return 1
    except Exception as e:
        logger.error(f"❌ No se pudo inicializar la BD: {e}")
        return 1

    # 2. Conectar con Odoo
    try:
        client = OdooClient()
        logger.info(f"📡 Conectando a Odoo ({client.url or 'N/A'})...")

        if not dry_run:
            if client.test_connection():
                logger.info("✅ Conexión con Odoo verificada exitosamente.")
            else:
                logger.error("❌ No se pudo conectar con Odoo. Verifica las credenciales en .env")
                return 1
        else:
            logger.info("📡 [DRY-RUN] Se omite la verificación de conexión con Odoo (config ya validada).")
    except OdooClientError as e:
        logger.error(f"❌ Error de configuración de Odoo: {e}")
        return 1

    # 3. Resolver corrida
    if ejecucion_id is not None:
        inicio = get_ejecucion_inicio(ejecucion_id)
        if inicio is None:
            logger.error(f"❌ No se encontró la ejecución con ID {ejecucion_id} en la BD local.")
            return 1
        corrida_id = ejecucion_id
    else:
        ultima = get_ultima_ejecucion_valida()
        if ultima is None:
            logger.error("❌ No se encontró ninguna corrida válida terminada con proyectos procesados.")
            return 1
        corrida_id = ultima["id"]
        inicio = ultima["timestamp_inicio"]

    logger.info(f"📌 Corrida usada: #{corrida_id} (inicio {inicio})")

    # 4. Resolver ubicación padre 'Production'
    parent = resolve_production_location(client)
    if parent is None:
        logger.error("❌ No se pudo resolver la ubicación padre 'Production' en Odoo. Abortando.")
        return 1

    # 5. Obtener proyectos de la corrida
    try:
        total_bd = get_project_count()
        projects = get_projects_desde(inicio)
    except Exception as e:
        logger.error(f"❌ Error leyendo la base de datos local: {e}")
        return 1

    if not projects:
        logger.warning(f"⚠️  La corrida #{corrida_id} no dejó proyectos para sincronizar.")
        return 0

    total_corrida = len(projects)
    logger.info(f"📂 Proyectos de la corrida: {total_corrida} (BD local: {total_bd})")

    if limit is not None and limit > 0:
        projects = projects[:limit]
        logger.info(f"✂️  Límite activo: se procesan {len(projects)} de {total_corrida}")

    # 6. Contadores de resultados
    stats = {"created": 0, "sin_cambios": 0, "aviso": 0, "error": 0}

    # 7. Recorrido plano proyecto por proyecto
    logger.info(f"\n🔄 Procesando {len(projects)} proyectos...")
    for i, proyecto in enumerate(projects, 1):
        nombre = proyecto.nombre
        logger.info(f"\n[{i}/{len(projects)}] Proyecto: '{nombre}'")
        _, accion = sync_one_location(client, proyecto, parent, dry_run=dry_run)
        if accion in stats:
            stats[accion] += 1
        else:
            stats["error"] += 1

    # 8. Resumen final
    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 70)
    if dry_run:
        logger.info("RESUMEN DE SIMULACIÓN (DRY-RUN)")
        logger.info("=" * 70)
        logger.info(f"  Duración: {elapsed:.1f} segundos")
        logger.info(
            f"  Ubicaciones — Creadas (se crearían): {stats['created']}, "
            f"Sin cambios: {stats['sin_cambios']}, "
            f"Avisos: {stats['aviso']}, "
            f"Errores: {stats['error']}"
        )
    else:
        logger.info("RESUMEN DE SINCRONIZACIÓN")
        logger.info("=" * 70)
        logger.info(f"  Duración: {elapsed:.1f} segundos")
        logger.info(
            f"  Ubicaciones — Creadas: {stats['created']}, "
            f"Sin cambios: {stats['sin_cambios']}, "
            f"Avisos: {stats['aviso']}, "
            f"Errores: {stats['error']}"
        )
    logger.info("=" * 70)

    if stats["error"] > 0:
        logger.warning(f"⚠️  La sincronización terminó con {stats['error']} error(es).")
        return 2
    else:
        logger.info("✅ Sincronización completada sin errores.")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Sincronización de ubicaciones de producción con Odoo vía API JSON-2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python odoo_sync.py                      # última corrida válida
  python odoo_sync.py --dry-run            # simulación real (solo lecturas)
  python odoo_sync.py --limit 1            # smoke test contra un solo proyecto
  python odoo_sync.py --ejecucion-id 39    # corrida puntual
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula la sincronización sin hacer cambios en Odoo ni en la BD local.",
    )
    parser.add_argument(
        "--only-projects",
        action="store_true",
        help="Obsoleto: ya no se crean tareas/productos (no-op).",
    )
    parser.add_argument(
        "--ejecucion-id",
        type=int,
        default=None,
        help="ID de corrida puntual a sincronizar (por defecto: última corrida válida).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita la cantidad de proyectos a procesar.",
    )
    args = parser.parse_args()

    exit_code = run_sync(
        dry_run=args.dry_run,
        only_projects=args.only_projects,
        ejecucion_id=args.ejecucion_id,
        limit=args.limit,
    )
    sys.exit(exit_code or 0)


if __name__ == "__main__":
    main()
