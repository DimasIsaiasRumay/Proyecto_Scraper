# main.py — Orquestador principal del scraper
import os
import sys
import argparse
import logging
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import config

# --- Habilitar import directo del módulo de sincronización con Odoo ---
# Antes se invocaba odoo_sync.py como subproceso separado (python odoo_sync.py).
# Se unifica en un solo proceso: se agrega odoo-integration/ al sys.path y se
# importa run_sync() directamente, así una sola ejecución de main.py hace
# scraping + sincronización sin depender de rutas relativas a un script externo.
_ODOO_INTEGRATION_DIR = os.path.normpath(
    os.path.join(config.BASE_DIR, "..", "odoo-integration")
)
if os.path.isdir(_ODOO_INTEGRATION_DIR) and _ODOO_INTEGRATION_DIR not in sys.path:
    sys.path.insert(0, _ODOO_INTEGRATION_DIR)

try:
    from odoo_sync import run_sync as run_odoo_sync
except ImportError:
    # El módulo de Odoo es opcional: si no está instalado (requests/python-dotenv
    # faltantes) o no existe la carpeta, el scraping sigue funcionando igual;
    # solo --sync quedará inhabilitado y se avisa al usarlo.
    run_odoo_sync = None
from models import Proyecto, Producto, ProductoItem, Material
from database import (
    init_db, iniciar_ejecucion, finalizar_ejecucion,
    obtener_checkpoint, guardar_checkpoint, limpiar_checkpoint,
    upsert_proyecto, upsert_producto, upsert_item, upsert_material,
    registrar_error_proyecto
)
from scraper import (
    setup_logger, login, extraer_proyectos, extraer_materiales,
    check_session_and_relogin, human_delay
)

logger = setup_logger()

# --- CONTROL DE LOCK (ANTI-SOLAPAMIENTO) ---

def acquire_lock():
    """Crea un archivo de lock para asegurar exclusión mutua."""
    if os.path.exists(config.LOCK_PATH):
        try:
            with open(config.LOCK_PATH, "r") as f:
                pid = f.read().strip()
            
            # Comprobar si el proceso del lock sigue activo en el sistema
            # En Windows os.kill(pid, 0) lanza un ProcessLookupError si no existe
            os.kill(int(pid), 0)
            logger.warning(f"Otra instancia del scraper ya se está ejecutando (PID: {pid}). Saliendo.")
            sys.exit(0)
        except (OSError, ValueError):
            # Proceso no existe, eliminar lock huérfano
            logger.info("Eliminando archivo de lock huérfano de una corrida anterior...")
            try:
                os.remove(config.LOCK_PATH)
            except Exception:
                pass
                
    # Crear nuevo lock con el PID actual
    with open(config.LOCK_PATH, "w") as f:
        f.write(str(os.getpid()))

def release_lock():
    """Elimina el archivo de lock al finalizar la ejecución."""
    if os.path.exists(config.LOCK_PATH):
        try:
            os.remove(config.LOCK_PATH)
        except Exception as e:
            logger.warning(f"No se pudo eliminar el archivo de lock: {e}")

# --- VALIDACIÓN DE VENTANA HORARIA ---

def esta_en_ventana_horaria() -> bool:
    """Verifica si la hora actual local está dentro de las ventanas permitidas."""
    now_str = datetime.now().strftime("%H:%M")
    for inicio, fin in config.TIME_WINDOWS:
        if inicio <= now_str <= fin:
            return True
    return False

# --- ORQUESTADOR PRINCIPAL ---

def main():
    parser = argparse.ArgumentParser(description="Bot Scraper de Fabricación")
    parser.add_argument(
        "--force", "-f", "--manual", "-m",
        action="store_true",
        help="Omitir el control de ventana horaria y forzar la ejecución manual de inmediato."
    )
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="Ejecución de prueba limitada a los primeros 3 proyectos para validación rápida."
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Ejecutar sincronización con Odoo al finalizar el scraping exitosamente."
    )
    args = parser.parse_args()

    # 1. Validar ventana de tiempo (si no se fuerza la ejecución)
    if not args.force:
        if not esta_en_ventana_horaria():
            logger.info(
                f"Fuera de la ventana horaria permitida para ejecución automática ({datetime.now().strftime('%H:%M')}). "
                f"Ventanas permitidas: {config.TIME_WINDOWS}. Use --force para ejecución manual. Saliendo."
            )
            sys.exit(0)
    else:
        logger.info("Ejecución forzada manualmente por el usuario. Omitiendo validación horaria.")

    # 2. Adquirir lock para evitar ejecuciones concurrentes
    acquire_lock()
    
    # 3. Inicializar base de datos
    conn = init_db(config.DB_PATH)
    ejecucion_id = iniciar_ejecucion(conn)
    logger.info(f"Iniciando ejecución ID: {ejecucion_id}")
    
    # 4. Verificar checkpoints
    checkpoint = obtener_checkpoint(conn)
    desde_proyecto = None
    if checkpoint:
        eid_prev, desde_proyecto = checkpoint
        logger.info(f"Se detectó una interrupción anterior. Se retomará desde el proyecto posterior a: '{desde_proyecto}'")

    proyectos_procesados_totales = 0
    materiales_procesados_totales = 0
    proyectos_fallidos = []  # Lista de proyectos que no pudieron procesarse
    estado_final = "ok"
    mensaje_error = None

    try:
        # 5. Iniciar Playwright con argumentos antidetect (Stealth)
        with sync_playwright() as p:
            logger.info("Iniciando navegador Chromium...")
            browser = p.chromium.launch(
                headless=config.HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled", # Desactivar flag webdriver
                    "--no-sandbox",
                    "--disable-setuid-sandbox"
                ]
            )
            
            # Contexto con Viewport Desktop grande y User-Agent real
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            # Ocultar webdriver en javascript de las páginas
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            page = context.new_page()
            
            # Login inicial
            login(page)
            
            # Extraer proyectos
            proyectos = extraer_proyectos(page)
            
            # Filtrar si hay checkpoint
            proyectos_a_procesar = proyectos
            if desde_proyecto:
                idx = -1
                for i, p_item in enumerate(proyectos):
                    if p_item.nombre == desde_proyecto:
                        idx = i
                        break
                if idx != -1:
                    logger.info(f"Omitiendo proyectos ya procesados. Empezando desde el siguiente a '{desde_proyecto}'")
                    proyectos_a_procesar = proyectos[idx + 1:]
                else:
                    logger.info(f"Proyecto '{desde_proyecto}' no encontrado en la lista actual. Procesando todos los proyectos.")
            
            logger.info(f"Proyectos pendientes por procesar en esta corrida: {len(proyectos_a_procesar)}")
            
            if args.test:
                logger.info("Modo de prueba activo (--test). Limitando el procesamiento a los primeros 3 proyectos.")
                proyectos_a_procesar = proyectos_a_procesar[:3]
            
            # 6. Loop de procesamiento de proyectos y materiales
            MAX_REINTENTOS = 3
            BACKOFF_BASE_SEGUNDOS = 5.0  # backoff exponencial: ~5s, ~10s, ~20s

            for proyecto in proyectos_a_procesar:
                success = False
                ultimo_error = None
                # Reintentos por proyecto: SOLO ante errores transitorios (timeouts
                # de Playwright por red/sesión/ERP lento). Un error que no sea de
                # timeout (KeyError, IndexError, etc. — típicamente un selector roto
                # o un cambio de estructura en el ERP) no se arregla reintentando,
                # así que se trata como permanente y se corta al primer intento en
                # vez de gastar los 3 reintentos igual.
                for intento in range(1, MAX_REINTENTOS + 1):
                    try:
                        check_session_and_relogin(page)

                        # Guardar Proyecto, Productos y Items
                        upsert_proyecto(conn, proyecto)
                        for producto in proyecto.productos:
                            producto_id = upsert_producto(conn, producto)
                            for item in producto.items:
                                upsert_item(conn, producto_id, item)

                        # Extraer y guardar Materiales
                        materiales = extraer_materiales(page, proyecto.nombre)
                        for material in materiales:
                            upsert_material(conn, material)

                        materiales_procesados_totales += len(materiales)
                        proyectos_procesados_totales += 1

                        # Guardar checkpoint en DB indicando éxito hasta este proyecto
                        guardar_checkpoint(conn, ejecucion_id, proyecto.nombre)

                        success = True
                        break  # Éxito, salir del loop de intentos
                    except PlaywrightTimeoutError as ex:
                        # Transitorio: reintentar con backoff exponencial.
                        ultimo_error = ex
                        if intento < MAX_REINTENTOS:
                            espera = BACKOFF_BASE_SEGUNDOS * (2 ** (intento - 1))
                            logger.warning(
                                f"Timeout transitorio (intento {intento}/{MAX_REINTENTOS}) "
                                f"para '{proyecto.nombre}': {ex}. Reintentando en ~{espera:.0f}s..."
                            )
                            human_delay(espera, espera + 3.0)
                            try:
                                login(page)
                            except Exception:
                                pass
                        else:
                            logger.warning(
                                f"Timeout transitorio persistente tras {MAX_REINTENTOS} "
                                f"intentos para '{proyecto.nombre}': {ex}"
                            )
                    except Exception as ex:
                        # Permanente: no se reintenta. Se loguea distinto (con
                        # traceback) para que sea evidente en el log que esto NO
                        # fue un problema de red sino algo que requiere revisión
                        # de código/selectores.
                        ultimo_error = ex
                        logger.error(
                            f"Error permanente (no transitorio, no se reintenta) "
                            f"procesando '{proyecto.nombre}': {ex}",
                            exc_info=True
                        )
                        break

                if not success:
                    # Registrar el error en la tabla de incidentes y continuar con el siguiente proyecto
                    error_detail = f"{ultimo_error}"
                    logger.error(f"Fallo persistente procesando proyecto '{proyecto.nombre}'. Registrando incidente y continuando con el siguiente...")
                    registrar_error_proyecto(conn, ejecucion_id, proyecto.nombre, error_detail)
                    proyectos_fallidos.append(proyecto.nombre)

                    # Guardar checkpoint para que en una futura reanudación no se reintente
                    guardar_checkpoint(conn, ejecucion_id, proyecto.nombre)
                    continue

                # Pausa aleatoria entre proyectos para simular comportamiento humano
                human_delay(config.DELAY_MIN * 1.5, config.DELAY_MAX * 1.5)
                
            # Fin del loop sin errores
            browser.close()
            
        # 7. Limpiar checkpoints si todo salió bien
        limpiar_checkpoint(conn)
        
        if proyectos_fallidos:
            estado_final = "completado_con_errores"
            mensaje_error = f"Proyectos con error ({len(proyectos_fallidos)}): {', '.join(proyectos_fallidos)}"
            logger.warning(f"Corrida completada con errores. Proyectos OK: {proyectos_procesados_totales}, "
                           f"Materiales: {materiales_procesados_totales}, Proyectos fallidos: {len(proyectos_fallidos)}")
            logger.warning(f"Proyectos que no pudieron procesarse: {', '.join(proyectos_fallidos)}")

            # Alerta de tasa de fallo: una corrida con muchos proyectos fallidos
            # probablemente no sea "mala suerte" repetida sino un problema
            # estructural (el ERP cambió algo) que merece revisión inmediata,
            # no quedar enterrado como un WARNING más entre cientos de líneas.
            total_intentados = len(proyectos_a_procesar)
            tasa_fallo = len(proyectos_fallidos) / total_intentados if total_intentados else 0
            if tasa_fallo > 0.2:
                logger.error(
                    f"⚠️  TASA DE FALLO ELEVADA: {tasa_fallo:.0%} de los proyectos de esta "
                    f"corrida fallaron ({len(proyectos_fallidos)}/{total_intentados}). Esto "
                    f"puede indicar un problema estructural (cambio de selectores/estado en "
                    f"el ERP) en vez de fallas puntuales de red. Revisar cuanto antes."
                )
        else:
            logger.info(f"Corrida completada exitosamente. Proyectos: {proyectos_procesados_totales}, Materiales: {materiales_procesados_totales}")

        # --- Sincronización con Odoo (si se solicitó con --sync) ---
        if args.sync:
            if run_odoo_sync is None:
                logger.warning(
                    "⚠️  Sincronización con Odoo solicitada (--sync) pero el módulo "
                    f"'odoo_sync' no se pudo importar desde {_ODOO_INTEGRATION_DIR}. "
                    "Verifica que odoo-integration/ exista y sus dependencias "
                    "(requests, python-dotenv) estén instaladas."
                )
            else:
                logger.info("Iniciando sincronización con Odoo (--sync activado)...")
                try:
                    sync_exit_code = run_odoo_sync(dry_run=False, only_projects=False)
                    if not sync_exit_code:
                        logger.info("✅ Sincronización con Odoo completada exitosamente.")
                    else:
                        logger.warning(f"⚠️  Sincronización con Odoo terminó con errores (código: {sync_exit_code})")
                except Exception as sync_err:
                    logger.error(f"❌ Error al ejecutar sincronización con Odoo: {sync_err}", exc_info=True)

    except Exception as err:
        estado_final = "parcial" if proyectos_procesados_totales > 0 else "error"
        mensaje_error = str(err)
        logger.error(f"Ejecución detenida por error: {mensaje_error}", exc_info=True)
        
    finally:
        # Registrar fin de ejecución
        finalizar_ejecucion(
            conn, ejecucion_id, estado_final,
            proyectos_procesados_totales, materiales_procesados_totales,
            mensaje_error
        )
        conn.close()
        release_lock()

if __name__ == "__main__":
    main()
