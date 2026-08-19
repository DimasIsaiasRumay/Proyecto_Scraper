# scraper.py — Lógica de extracción de datos con Playwright (síncrono)
import os
import sys
import time
import random
import logging
from datetime import datetime
from typing import List, Optional
from playwright.sync_api import Page, Locator, TimeoutError as PlaywrightTimeoutError

from config import (
    URL_LOGIN, URL_PROYECTOS, URL_MATERIALES, USERNAME, PASSWORD,
    TIMEOUT_NAV, TIMEOUT_ELEMENT, DELAY_MIN, DELAY_MAX,
    LOG_PATH, LOG_MAX_BYTES, LOG_BACKUP_COUNT
)
from models import Proyecto, Producto, ProductoItem, Material
from database import upsert_proyecto, upsert_producto, upsert_material, guardar_checkpoint
from parsing import parse_date, parse_float

# Módulo de logging compartido con odoo-integration (ver common/logging_utils.py).
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from common.logging_utils import setup_rotating_logger

logger = logging.getLogger("scraper")

def setup_logger():
    """Configura el logger rotativo para toda la aplicación (ver common/logging_utils.py)."""
    return setup_rotating_logger(
        name="scraper",
        log_path=LOG_PATH,
        max_bytes=LOG_MAX_BYTES,
        backup_count=LOG_BACKUP_COUNT,
        file_level=logging.DEBUG,
        console_level=logging.INFO,
    )

# --- UTILERÍAS DE PARSEO Y SIMULACIÓN HUMANA ---

def human_delay(min_sec: float = DELAY_MIN, max_sec: float = DELAY_MAX):
    """Introduce un retraso aleatorio para imitar el comportamiento humano."""
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)

# parse_date() y parse_float() viven ahora en parsing.py (sin dependencias de
# config/playwright) para que los tests de parseo se puedan importar sin .env.
# Se re-exportan acá para no romper `from scraper import parse_date`.

# --- ACCIONES PRINCIPALES ---

def login(page: Page):
    """Inicia sesión simulando interacción humana."""
    logger.info("Intentando iniciar sesión...")
    page.goto(URL_LOGIN, timeout=TIMEOUT_NAV)
    human_delay(1.5, 3.0)
    
    # Verificar si ya estamos logueados
    try:
        if page.locator("#userfullname").is_visible():
            user_name = page.inner_text("#userfullname").strip()
            logger.info(f"Sesión activa detectada. Logueado como: {user_name}")
            return
    except Exception:
        pass
        
    page.wait_for_selector("#username", timeout=TIMEOUT_ELEMENT)
    
    # Escribir usuario y contraseña simulando tipeo humano
    page.locator("#username").click()
    page.locator("#username").fill("")
    page.locator("#username").type(USERNAME, delay=random.uniform(0.05, 0.15))
    human_delay(0.5, 1.2)
    
    page.locator("#password").click()
    page.locator("#password").fill("")
    page.locator("#password").type(PASSWORD, delay=random.uniform(0.05, 0.15))
    human_delay(0.8, 1.5)
    
    # Clic en botón login
    page.click("#login")
    human_delay(1.0, 2.0)
    
    # Validar resultado
    try:
        page.wait_for_selector("#userfullname", timeout=TIMEOUT_ELEMENT)
        user_name = page.inner_text("#userfullname").strip()
        logger.info(f"Sesión iniciada con éxito. Usuario: {user_name}")
    except Exception as e:
        if page.locator("#msg").is_visible():
            error_msg = page.inner_text("#msg").strip()
            logger.error(f"Error de autenticación: {error_msg}")
            raise Exception(f"Login fallido: {error_msg}")
        else:
            logger.error("No se pudo validar el login (timeout).")
            raise e

def check_session_and_relogin(page: Page):
    """Valida la sesión actual y reconecta si ha expirado."""
    is_logged_in = False
    try:
        is_logged_in = page.locator("#userfullname").is_visible()
    except Exception:
        pass
        
    if not is_logged_in:
        logger.info("Sesión perdida o expirada. Reconectando...")
        login(page)

def extraer_proyectos(page: Page) -> List[Proyecto]:
    """Navega y extrae la lista de proyectos, sus productos y sus items hijos."""
    check_session_and_relogin(page)
    logger.info("Navegando a la sección de Proyectos...")
    page.goto(URL_PROYECTOS, timeout=TIMEOUT_NAV)
    human_delay()
    
    page.wait_for_selector("#tablaTree", timeout=TIMEOUT_ELEMENT)
    
    # Seleccionar Estado Proyecto (Material OK y Sin Material)
    page.select_option("#estado_proyecto", value=["Material OK", "Sin Material"])
    human_delay(0.5, 1.0)
    
    # Buscar
    page.click("#find")
    logger.info("Esperando que cargue la tabla de proyectos...")
    
    # Esperar a que la tabla tenga datos
    page.wait_for_selector("#proyectos tr", timeout=TIMEOUT_ELEMENT)
    human_delay(1.0, 2.0)
    
    rows = page.locator("#proyectos tr").all()
    logger.info(f"Se encontraron {len(rows)} filas en la tabla de proyectos.")
    
    proyectos: List[Proyecto] = []
    proyecto_tt_ids = set()
    current_proyecto: Optional[Proyecto] = None
    current_producto: Optional[Producto] = None
    
    for row in rows:
        try:
            # Determinar si es fila padre o hijo mediante treetable properties
            tt_id = row.get_attribute("data-tt-id")
            tt_parent_id = row.get_attribute("data-tt-parent-id")
            
            tds = row.locator("td").all()
            if not tds:
                continue

            # Guarda defensiva: la extracción de columnas es posicional
            # (tds[N]) porque así está el DOM del ERP; si el número de
            # columnas cambia (ej. el ERP agrega/quita una columna), mejor
            # fallar con un mensaje claro que apunte al problema real que
            # dejar que un IndexError genérico se confunda con un timeout
            # de red en los logs.
            min_cols_esperadas = 3 if not tt_parent_id else 6
            if len(tds) < min_cols_esperadas:
                logger.warning(
                    f"Fila de proyectos con {len(tds)} columnas (se esperaban >= "
                    f"{min_cols_esperadas}); posible cambio de estructura en el ERP. "
                    f"tt_id={tt_id!r} tt_parent_id={tt_parent_id!r}. Fila omitida."
                )
                continue

            if not tt_parent_id:
                # --- PROYECTO PADRE (Nivel 1) ---
                if tt_id:
                    proyecto_tt_ids.add(tt_id)

                # Estructura Col 0: <span class="folder">NombreProyecto <br> <span>(Cliente)</span></span>
                td0_html = tds[0].inner_html()
                
                # Parsear nombre y cliente
                # Si hay sub-elementos de tipo br y span para el cliente
                td0_text = tds[0].inner_text().strip()
                lines = [l.strip() for l in td0_text.split("\n") if l.strip()]
                
                proyecto_nombre = lines[0] if lines else "N/A"
                proyecto_cliente = "N/A"
                if len(lines) > 1:
                    # Remover paréntesis del cliente si los tiene
                    proyecto_cliente = lines[1].replace("(", "").replace(")", "").strip()
                
                # Debido a colspan="4" en fila padre, las columnas se desplazan
                # tds[0] = Nombre/Cliente
                # tds[1] = Colspan de espacio
                # tds[2] = Estado Proyecto (según DOM inspeccionado)
                proyecto_estado = tds[2].inner_text().strip()
                
                current_proyecto = Proyecto(
                    nombre=proyecto_nombre,
                    cliente=proyecto_cliente,
                    estado=proyecto_estado,
                    productos=[]
                )
                current_producto = None
                proyectos.append(current_proyecto)
                
            elif tt_parent_id in proyecto_tt_ids:
                # --- PRODUCTO HIJO (Nivel 2) ---
                if not current_proyecto:
                    continue # Fila huérfana, omitir
                    
                nombre = tds[0].inner_text().strip()
                cantidad = tds[1].inner_text().strip()
                solicitud = tds[2].inner_text().strip()
                entrega_fc = tds[3].inner_text().strip()
                entrega = tds[4].inner_text().strip()
                estado = tds[5].inner_text().strip()
                
                current_producto = Producto(
                    proyecto_nombre=current_proyecto.nombre,
                    nombre=nombre,
                    cantidad=parse_float(cantidad),
                    solicitud=parse_date(solicitud),
                    entrega_fc=parse_date(entrega_fc),
                    entrega=parse_date(entrega),
                    estado=estado,
                    items=[]
                )
                current_proyecto.productos.append(current_producto)
                
            else:
                # --- ITEM HIJO (Nivel 3) ---
                if not current_proyecto:
                    continue
                    
                nombre = tds[0].inner_text().strip()
                cantidad = tds[1].inner_text().strip()
                solicitud = tds[2].inner_text().strip()
                entrega_fc = tds[3].inner_text().strip()
                entrega = tds[4].inner_text().strip()
                estado = tds[5].inner_text().strip()
                
                item = ProductoItem(
                    nombre=nombre,
                    cantidad=parse_float(cantidad),
                    solicitud=parse_date(solicitud),
                    entrega_fc=parse_date(entrega_fc),
                    entrega=parse_date(entrega),
                    estado=estado
                )
                if current_producto:
                    current_producto.items.append(item)
                else:
                    logger.warning(f"Fila de Item huérfana sin Producto activo (parent_id: {tt_parent_id}): {nombre}")
                
        except Exception as row_ex:
            logger.warning(f"Error procesando fila de proyectos: {row_ex}")
            continue
            
    logger.info(f"Extracción de proyectos completada. Total proyectos raíz: {len(proyectos)}")
    return proyectos

# --- Patrones de ID dinámico para los campos de materiales ---
# Antes estos ~12 selectores estaban repetidos inline dentro de
# extraer_materiales_de_seccion() (#proveedor_{mid}, #{pfx}cant_{mid}, etc.),
# cada uno con su propio armado de string. Centralizarlos acá significa que
# si el ERP cambia el nombre de un campo, el fix es una línea en esta tabla
# en vez de tener que rastrear la llamada suelta correspondiente en medio
# de la función.
#
# Cada entrada define:
#   base:      nombre base del id en el DOM (sin prefijo ni sufijo _{mid})
#   prefixed:  si True, los suministros usan el prefijo "suministro_" antes
#              del nombre base (verificado en vivo contra el ERP); si False,
#              el id es igual para items y suministros.
#   tipos:     a qué tipos de material aplica este campo (algunos, como
#              desperdicio_12/validacion_diseno, solo existen para "item").
MATERIAL_ID_PATTERNS = {
    "proveedor":         {"base": "proveedor",       "prefixed": False, "tipos": {"item", "suministro"}},
    "cantidad":          {"base": "cant",             "prefixed": True,  "tipos": {"item", "suministro"}},
    "desperdicio_12":    {"base": "cant_desp",        "prefixed": False, "tipos": {"item"}},
    "validacion_diseno": {"base": "val_dis",          "prefixed": False, "tipos": {"item"}},
    "stock_chapa_barras":{"base": "stock",            "prefixed": True,  "tipos": {"item", "suministro"}},
    "comprar":           {"base": "comprar",          "prefixed": True,  "tipos": {"item", "suministro"}},
    "precio_sw":         {"base": "precio_actual",    "prefixed": True,  "tipos": {"item", "suministro"}},
    "precio_compra":     {"base": "total_comprado",   "prefixed": True,  "tipos": {"item", "suministro"}},
    "orden_compra":      {"base": "orden_compra",     "prefixed": False, "tipos": {"item", "suministro"}},
    "numero_factura":    {"base": "numero_factura",   "prefixed": False, "tipos": {"item", "suministro"}},
    "estado_compra":     {"base": "estado_compra",    "prefixed": True,  "tipos": {"item", "suministro"}},
    "comentarios":       {"base": "comentario",       "prefixed": True,  "tipos": {"item", "suministro"}},
}

# Fase 3 del fallback a "Editar Formulario" (ver docs/plan_fallback_formulario.md).
# MATERIAL_ID_PATTERNS está armado sobre los IDs de "Visualizar Detalle". El
# reconocimiento en vivo contra el ERP real (Fase 2 del plan, reproducido en
# los 3 proyectos comparados: el sano y los 2 rotos) confirmó que en "Editar
# Formulario" 4 de esos 12 campos usan un ID DISTINTO, no solo un tag
# distinto. Esta tabla registra SOLO las diferencias — cualquier campo que no
# aparece acá comparte base/prefixed entre las dos vistas.
MATERIAL_ID_OVERRIDES_FORMULARIO = {
    "precio_sw":      {"base": "precio_sw"},       # detalle: precio_actual
    "precio_compra":  {"base": "precio_comprado"}, # detalle: total_comprado
    "orden_compra":   {"prefixed": True},           # detalle: sin prefijo, incluso en suministro
    "numero_factura": {"prefixed": True},           # detalle: sin prefijo, incluso en suministro
}


def _material_field_id(campo: str, mid: str, tipo: str, vista: str = "detalle") -> str:
    """Arma el selector #id real en el DOM para un campo de MATERIAL_ID_PATTERNS.

    `vista` distingue "detalle" (Visualizar Detalle, el camino normal) de
    "formulario" (Editar Formulario, fallback de scraper.py:~448 cuando
    Detalle no carga) — ver MATERIAL_ID_OVERRIDES_FORMULARIO arriba.
    """
    spec = dict(MATERIAL_ID_PATTERNS[campo])
    if vista == "formulario" and campo in MATERIAL_ID_OVERRIDES_FORMULARIO:
        spec.update(MATERIAL_ID_OVERRIDES_FORMULARIO[campo])
    pfx = "suministro_" if (spec["prefixed"] and tipo == "suministro") else ""
    return f"#{pfx}{spec['base']}_{mid}"


def _leer_valor_campo(page: Page, selector: str) -> str:
    """Lee el valor de un campo del ERP sin importar si es texto plano
    (<span>/<td>), un <input>/<textarea> o un <select>.

    Hace falta desde que "Editar Formulario" (fallback de "Visualizar
    Detalle") resultó usar <input>/<select> para varios campos que en
    Detalle son <span> de solo texto (verificado en vivo, Fase 2 de
    docs/plan_fallback_formulario.md): inner_text() sobre un <input> siempre
    devuelve "" sin lanzar excepción, lo que corrompería esos campos en
    silencio (se guardarían como NULL en la BD) si no se distinguiera el tag.

    Solo lectura: usa input_value()/inner_text(), nunca dispara eventos
    onchange/onblur del JS del ERP.
    """
    loc = page.locator(selector)
    if loc.count() == 0:
        # A diferencia de antes (dejar que .inner_text() sobre un locator
        # vacío tire un TimeoutError que descarta el material entero por el
        # try/except de extraer_materiales_de_seccion), acá se degrada campo
        # por campo: se guarda "" (-> None tras parse) pero el resto del
        # material se conserva, y queda constancia explícita en el log de
        # que ese campo puntual no resolvió.
        logger.warning(f"_leer_valor_campo: selector '{selector}' no resolvió ningún elemento; se guarda vacío.")
        return ""

    tag = loc.first.evaluate("el => el.tagName")
    if tag in ("INPUT", "TEXTAREA"):
        return (loc.first.input_value() or "").strip()
    if tag == "SELECT":
        texto = loc.first.evaluate(
            "el => el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : ''"
        )
        return (texto or "").strip()
    return loc.first.inner_text().strip()


def extraer_materiales_de_seccion(
    page: Page, ids: List[str], tipo: str, proyecto_nombre: str, vista: str = "detalle"
) -> List[Material]:
    """Helper para extraer materiales (ítems o suministros) por sus IDs en el DOM.

    `vista`: "detalle" (Visualizar Detalle, default) o "formulario" (Editar
    Formulario, fallback). Ver MATERIAL_ID_OVERRIDES_FORMULARIO — 4 de los 12
    campos resuelven a un ID distinto según la vista.
    """
    materiales = []
    for mid in ids:
        mid = mid.strip()
        if not mid:
            continue
        try:
            # Ubicar primer TD que contiene el código y descripción. El
            # selector de "proveedor" está duplicado en el DOM de Formulario
            # (aparece también, con el mismo id, en el ícono "Agregar
            # Proveedor" de una columna posterior — verificado en vivo, Fase
            # 2 del plan) pero al ser :has() + .first sobre orden del DOM,
            # sigue resolviendo al primer <td> de la fila (el de la
            # descripción), que es el que importa acá.
            selector_proveedor = _material_field_id("proveedor", mid, tipo, vista=vista)
            td0 = page.locator(f"td:has({selector_proveedor})")
            if td0.count() == 0:
                continue

            # Extraer código y descripción del primer span en td0
            item_text = td0.locator("span").first.inner_text().strip()
            # "Editar Formulario" envuelve el código+descripción entre
            # paréntesis ("(MP_0042 - Perfil UPN100 )"), cosa que "Visualizar
            # Detalle" no hace (verificado en vivo, Fase 2 del plan). Se
            # recorta solo si están los dos paréntesis en los extremos, para
            # no tocar un nombre de material que legítimamente empiece o
            # termine con paréntesis en Detalle.
            if item_text.startswith("(") and item_text.endswith(")"):
                item_text = item_text[1:-1].strip()
            if " - " in item_text:
                parts = item_text.split(" - ", 1)
                codigo_mp = parts[0].strip()
                descripcion = parts[1].strip()
            else:
                codigo_mp = "N/A"
                descripcion = item_text

            # Extraer cada campo aplicable a este tipo usando la tabla de patrones.
            valores = {}
            for campo, spec in MATERIAL_ID_PATTERNS.items():
                if tipo not in spec["tipos"]:
                    valores[campo] = None
                    continue
                selector = _material_field_id(campo, mid, tipo, vista=vista)
                valores[campo] = _leer_valor_campo(page, selector)

            proveedor = valores["proveedor"]
            cantidad = valores["cantidad"]
            desperdicio_12 = valores["desperdicio_12"]
            validacion_diseno = valores["validacion_diseno"]
            stock_chapa_barras = valores["stock_chapa_barras"]
            comprar = valores["comprar"]
            precio_sw = valores["precio_sw"]
            precio_compra = valores["precio_compra"]
            orden_compra = valores["orden_compra"]
            numero_factura = valores["numero_factura"]
            estado_compra = valores["estado_compra"]
            comentarios = valores["comentarios"]

            materiales.append(Material(
                proyecto_nombre=proyecto_nombre,
                tipo=tipo,
                codigo_mp=codigo_mp,
                descripcion=descripcion,
                proveedor=proveedor if proveedor else None,
                cantidad=parse_float(cantidad),
                desperdicio_12=parse_float(desperdicio_12) if desperdicio_12 else None,
                validacion_diseno=parse_float(validacion_diseno) if validacion_diseno else None,
                stock_chapa_barras=parse_float(stock_chapa_barras),
                comprar=parse_float(comprar),
                precio_sw=parse_float(precio_sw),
                precio_compra=parse_float(precio_compra),
                orden_compra=orden_compra if orden_compra else None,
                numero_factura=numero_factura if numero_factura else None,
                estado_compra=estado_compra,
                comentarios=comentarios if comentarios else None
            ))
        except Exception as mat_ex:
            logger.warning(f"Error procesando material ID {mid} ({tipo}) en proyecto {proyecto_nombre}: {mat_ex}")
            continue
    return materiales

def extraer_materiales(page: Page, proyecto_nombre: str) -> List[Material]:
    """Busca un proyecto en la página de Materiales y extrae su detalle dinámico."""
    check_session_and_relogin(page)
    logger.info(f"Buscando materiales para proyecto: {proyecto_nombre}...")
    page.goto(URL_MATERIALES, timeout=TIMEOUT_NAV)
    human_delay()
    
    page.wait_for_selector("#nombre", timeout=TIMEOUT_ELEMENT)
    
    # Seleccionar Estado Proyecto (Material OK y Sin Material)
    page.select_option("#estado_proyecto", value=["Material OK", "Sin Material"])
    human_delay(0.5, 1.0)
    
    # Buscar por nombre de proyecto exacto
    page.locator("#nombre").fill(proyecto_nombre)
    human_delay(0.5, 1.0)
    page.click("#find")
    
    # Esperar resultados. Si no aparece ninguna fila, lo más probable (verificado
    # contra el ERP en vivo para proyectos como OP_CLIENTE_B_BANQUINAS) es que el
    # proyecto simplemente no tiene datos de logística/materiales cargados todavía,
    # no que el selector esté roto. Se trata como "sin materiales" en vez de como
    # fallo, para no gastar los 3 reintentos de main.py ni marcar el proyecto como
    # fallido cada corrida.
    try:
        page.wait_for_selector("#tablaTree tbody tr", timeout=TIMEOUT_ELEMENT)
    except PlaywrightTimeoutError:
        logger.warning(
            f"Proyecto '{proyecto_nombre}': la búsqueda de materiales no devolvió "
            f"ninguna fila (#tablaTree vacío). Probablemente el proyecto no tiene "
            f"datos de logística/materiales cargados en el ERP. Se omite sin reintentar."
        )
        return []
    human_delay(0.8, 1.5)

    rows = page.locator("#tablaTree tbody tr").all()
    target_row = None
    
    for row in rows:
        tds = row.locator("td").all()
        if tds:
            name_text = tds[0].inner_text().strip().split("\n")[0].strip()
            if name_text == proyecto_nombre:
                target_row = row
                break
                
    if not target_row:
        logger.warning(f"No se encontró fila de materiales para: '{proyecto_nombre}'")
        return []
        
    # Clic en el icono de Visualizar Detalle
    preview_btn = target_row.locator("img[title='Visualizar Detalle']")
    if preview_btn.count() == 0:
        logger.warning(f"No se encontró ícono de Visualizar Detalle para: '{proyecto_nombre}'")
        return []

    # Investigado en vivo: la carga de #detalleProyecto vía AJAX al hacer clic
    # en "Visualizar Detalle" falla de forma intermitente en el ERP (a veces
    # HTTP 500 del servidor, a veces el clic ni siquiera dispara la petición).
    # No es un selector roto del scraper — es el ERP fallando al renderizar el
    # detalle para ciertos proyectos. Además, cuando la petición AJAX falla,
    # el propio JS del ERP deja visible su modal de "cargando"
    # (.jquery-loading-modal) sin ocultarlo, y ese overlay bloquea los clics
    # siguientes ("subtree intercepts pointer events") — por eso reintentar
    # el clic sin más no alcanza: hay que limpiar el overlay atascado antes.
    MAX_INTENTOS_DETALLE = 2
    detalle_cargo = False
    for intento_detalle in range(1, MAX_INTENTOS_DETALLE + 1):
        if intento_detalle > 1:
            # Limpiar cualquier modal de "cargando" que haya quedado
            # atascado de un intento anterior fallido, para que el clic no
            # quede esperando 30s a que un elemento invisible-en-teoría
            # (pero bloqueante) desaparezca solo.
            page.evaluate("document.querySelectorAll('.jquery-loading-modal').forEach(el => el.remove())")
            human_delay(2.0, 4.0)
        preview_btn.first.click()
        logger.info(f"Esperando que cargue la sección de detalleProyecto (intento {intento_detalle}/{MAX_INTENTOS_DETALLE})...")
        try:
            page.wait_for_selector("#detalleProyecto table", timeout=TIMEOUT_ELEMENT)
            detalle_cargo = True
            break
        except PlaywrightTimeoutError:
            if intento_detalle < MAX_INTENTOS_DETALLE:
                logger.warning(
                    f"'{proyecto_nombre}': la carga de detalleProyecto no respondió en "
                    f"{TIMEOUT_ELEMENT}ms (falla intermitente conocida del ERP). "
                    f"Reintentando el clic..."
                )
            # Antes acá iba un `else: raise` directo tras agotar los
            # MAX_INTENTOS_DETALLE intentos. Ahora, antes de dar el proyecto
            # por perdido, se prueba el fallback de "Editar Formulario" (ver
            # _intentar_fallback_formulario y docs/plan_fallback_formulario.md
            # Fase 4) — si tampoco carga, se sigue lanzando la misma
            # excepción de siempre más abajo, así que el comportamiento para
            # un ERP realmente caído no cambia.

    vista = "detalle"
    if not detalle_cargo:
        if _intentar_fallback_formulario(page, target_row, proyecto_nombre):
            detalle_cargo = True
            vista = "formulario"
        else:
            raise PlaywrightTimeoutError(
                f"Timeout esperando #detalleProyecto table para '{proyecto_nombre}' "
                f"tras {MAX_INTENTOS_DETALLE} intentos de 'Visualizar Detalle' y el "
                f"fallback a 'Editar Formulario'."
            )
    human_delay(1.0, 2.0)

    # Fase 5 del plan (guardas anti-escritura): mientras se lee "Editar
    # Formulario", se vigila que no aparezca ninguna request de escritura
    # ADEMÁS de la que abre el formulario. Esa primera (el clic de
    # _intentar_fallback_formulario) ya terminó y quedó fuera de esta
    # ventana — es la única esperada, y la Fase 2 del plan ya comparó su
    # respuesta contra la del endpoint de solo lectura sin encontrar
    # evidencia de que persista nada. Cualquier POST/PUT/DELETE/PATCH que
    # aparezca DESPUÉS, mientras solo se están leyendo campos, es indicio de
    # algo no esperado (a diferencia del reconocimiento de la Fase 2, este
    # monitor corre en cada corrida real, no solo en la exploración manual).
    monitor_escrituras = _MonitorEscriturasFormulario(page) if vista == "formulario" else None

    # Obtener las listas de IDs de la fila
    hdn_items = page.locator("#hdnItemsId").get_attribute("value")
    hdn_suministros = page.locator("#hdnSuministrosId").get_attribute("value")

    item_ids = [x.strip() for x in hdn_items.split(",") if x.strip()] if hdn_items else []
    suministro_ids = [x.strip() for x in hdn_suministros.split(",") if x.strip()] if hdn_suministros else []

    logger.info(f"Proyecto '{proyecto_nombre}': {len(item_ids)} items, {len(suministro_ids)} suministros encontrados.")

    materiales = []
    # Procesar ambas secciones
    materiales.extend(extraer_materiales_de_seccion(page, item_ids, "item", proyecto_nombre, vista=vista))
    materiales.extend(extraer_materiales_de_seccion(page, suministro_ids, "suministro", proyecto_nombre, vista=vista))

    if monitor_escrituras is not None:
        monitor_escrituras.detener()
        if monitor_escrituras.hubo_escrituras():
            # Por precaución se descartan los materiales ya leídos: no hay
            # forma de saber desde acá si la escritura detectada tocó (o no)
            # los datos que se acaban de leer, así que no se puede confiar
            # en ellos. El proyecto queda como fallido, igual que si
            # "Editar Formulario" no hubiera cargado — main.py ya sabe
            # reintentar y, si persiste, registrar el incidente.
            logger.error(
                f"Proyecto '{proyecto_nombre}': se detectó actividad de escritura "
                f"inesperada mientras se leía 'Editar Formulario' (más allá de la "
                f"apertura inicial, ya evidenciada como inofensiva en "
                f"docs/plan_fallback_formulario.md Fase 2): "
                f"{monitor_escrituras.reporte()}. Se descartan los {len(materiales)} "
                f"material(es) recién leídos por precaución."
            )
            raise RuntimeError(
                f"Actividad de escritura inesperada al leer 'Editar Formulario' "
                f"para '{proyecto_nombre}'; ver el log de ERROR justo arriba."
            )

    return materiales


def _intentar_fallback_formulario(page: Page, target_row: Locator, proyecto_nombre: str) -> bool:
    """Fallback de extraer_materiales() cuando 'Visualizar Detalle' se agota
    tras MAX_INTENTOS_DETALLE intentos (ver el comentario sobre la falla
    intermitente conocida del ERP, unas líneas más arriba). Abre 'Editar
    Formulario' en su lugar.

    SOLO LECTURA: nunca hace fill()/select_option()/check()/press() ni
    clickea "Guardar" — el único click acá es para ABRIR el formulario, no
    para modificarlo. Investigado en vivo contra el ERP real
    (docs/plan_fallback_formulario.md, Fase 2): el endpoint que dispara este
    ícono del lado del servidor se llama "actualizar..." (nombre engañoso),
    pero comparado con el endpoint de solo lectura "visualizar...", ambos
    devuelven la misma forma de respuesta (un fragmento HTML para inyectar
    en '#detalleProyecto') sin ningún flag de éxito de guardado ni dato
    persistido — no hay evidencia de que abrir el formulario escriba nada.

    "Editar Formulario" comparte el mismo contenedor '#detalleProyecto
    table' que "Visualizar Detalle" (verificado en vivo), así que no hace
    falta un selector de espera distinto.

    Devuelve True si el formulario cargó, False si también falló (en cuyo
    caso el llamador sigue tratando el proyecto como fallido, igual que
    antes de que existiera este fallback).
    """
    editar_btn = target_row.locator("img[title='Editar Formulario']")
    if editar_btn.count() == 0:
        logger.warning(
            f"'{proyecto_nombre}': no se encontró el ícono 'Editar Formulario' "
            f"para el fallback tras agotar 'Visualizar Detalle'."
        )
        return False

    logger.warning(
        f"'{proyecto_nombre}': 'Visualizar Detalle' no cargó tras los reintentos. "
        f"Probando fallback de solo lectura vía 'Editar Formulario'..."
    )
    page.evaluate("document.querySelectorAll('.jquery-loading-modal').forEach(el => el.remove())")
    human_delay(1.0, 2.0)
    editar_btn.first.click()
    try:
        page.wait_for_selector("#detalleProyecto table", timeout=TIMEOUT_ELEMENT)
    except PlaywrightTimeoutError:
        logger.warning(f"'{proyecto_nombre}': el fallback a 'Editar Formulario' también agotó el timeout.")
        return False

    logger.warning(
        f"Proyecto '{proyecto_nombre}': 'Visualizar Detalle' no estuvo disponible, "
        f"extraído vía 'Editar Formulario' (solo lectura) en su lugar."
    )
    return True


class _MonitorEscriturasFormulario:
    """Guarda de la Fase 5 (docs/plan_fallback_formulario.md): mientras
    extraer_materiales() lee campos por la vía "Editar Formulario", vigila
    la red por cualquier request de escritura que no sea la ya esperada
    (la que abre el formulario, disparada por el clic en
    _intentar_fallback_formulario — esa ya terminó y quedó fuera de la
    ventana de este monitor porque se instancia después).

    Solo lectura sobre el tráfico: un listener de `page.on("request")` no
    intercepta ni cancela nada, solo observa lo que el navegador ya iba a
    mandar de todas formas.
    """

    METODOS_ESCRITURA = {"POST", "PUT", "DELETE", "PATCH"}

    def __init__(self, page: Page):
        self.page = page
        self.detectadas = []
        page.on("request", self._on_request)

    def _on_request(self, request):
        if request.method in self.METODOS_ESCRITURA:
            self.detectadas.append((request.method, request.url))

    def detener(self):
        try:
            self.page.remove_listener("request", self._on_request)
        except Exception:
            # No debe poder tumbar la corrida por un detalle de limpieza
            # del listener — en el peor caso queda un listener de más
            # colgado hasta que cierre el browser, no una escritura sin
            # detectar (el reporte ya se calculó con lo que había hasta acá).
            pass

    def hubo_escrituras(self) -> bool:
        return bool(self.detectadas)

    def reporte(self) -> str:
        return "; ".join(f"{metodo} {url}" for metodo, url in self.detectadas)
