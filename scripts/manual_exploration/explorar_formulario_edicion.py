"""
Script de exploración manual (NO es parte de un test suite automatizado).

SOLO LECTURA. No hace fill()/select_option()/check()/press() ni submit sobre
ningún campo del ERP en ningún momento. Es una regla dura de este script, no
solo una intención: ver la sección "Guardas de solo lectura" más abajo.

Golpea el ERP de PRODUCCIÓN en vivo. Objetivo: Fase 2 de
docs/plan_fallback_formulario.md — comparar el DOM de "Visualizar Detalle"
contra el de "Editar Formulario" para los mismos materiales, y verificar que
"Editar Formulario" carga en los dos proyectos que hoy fallan con
"Visualizar Detalle".

Para cada uno de los 12 campos de scraper.MATERIAL_ID_PATTERNS, en ambas
vistas, reporta: si el elemento existe, su tagName, qué devuelve
inner_text() y qué devuelve input_value()/valor de <select> — la
comparación que decide si extraer_materiales_de_seccion() puede reusarse tal
cual sobre el formulario o si hace falta un lector agnóstico al tipo de
elemento (Fase 3 del plan).

También vigila la red mientras el formulario está abierto: si el ERP dispara
un POST/PUT/DELETE al abrir o mientras se lee el formulario, lo reporta como
ADVERTENCIA — sería indicio de que "solo abrir" el formulario ya escribe
algo, y el plan se frena ahí (ver Fase 2, "Punto de decisión").

Uso:
    python explorar_formulario_edicion.py
    python explorar_formulario_edicion.py --proyecto-sano "OP-AMX-EMIX-070826-0001"
    python explorar_formulario_edicion.py --solo-rotos

No lo ejecute pytest/CI automáticamente.
"""
import argparse
import os
import sys
import asyncio
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, Page

sys.path.append(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scraper-fabricacion")))
import config
# MATERIAL_ID_PATTERNS y _material_field_id son solo tablas/funciones puras
# (dict lookups y armado de strings) — importarlas acá no ejecuta nada de
# Playwright, así que no hay conflicto entre el scraper.py síncrono y este
# script asíncrono.
from scraper import MATERIAL_ID_PATTERNS, _material_field_id

# Proyecto de referencia: procesado OK en la corrida del 18/08/2026
# (ejecución id 39) con "Visualizar Detalle" funcionando normal — 4 items,
# 2 suministros. Es el mismo de la captura que compartió el usuario.
PROYECTO_SANO_DEFAULT = "OP-AMX-EMIX-070826-0001"

# Los dos proyectos que fallan con "Visualizar Detalle" desde la corrida del
# 18/08/2026 (uno de ellos, recurrente desde el 30/06/2026).
PROYECTOS_ROTOS = [
    "OP-ING-EPLIQ-070826-0001",
    "OP_CLARO_Complemento COWRoja_2906261616",
]

# Título del ícono de edición tal como lo marcó el usuario en la UI. Si el
# ERP usa un texto distinto, el script igual lista todos los íconos de la
# columna de Acciones antes de intentar el clic, así que un mismatch queda
# visible en la salida en vez de fallar en silencio.
TITULO_ICONO_EDITAR = "Editar Formulario"
TITULO_ICONO_DETALLE = "Visualizar Detalle"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Métodos que, si se ven en la red mientras se explora, son señal de
# escritura. GET/HEAD/OPTIONS no cuentan.
METODOS_ESCRITURA = {"POST", "PUT", "DELETE", "PATCH"}


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class MonitorEscrituras:
    """Registra cualquier request de escritura vista mientras está activo.

    No bloquea nada — playwright no ofrece "solo observar sin poder
    interceptar" gratis, así que esto es un listener de solo lectura sobre
    el tráfico, nunca modifica ni cancela requests.
    """

    def __init__(self, page: Page):
        self.page = page
        self.detectadas = []
        page.on("request", self._on_request)

    def _on_request(self, request):
        if request.method in METODOS_ESCRITURA:
            self.detectadas.append((request.method, request.url))

    def reporte(self) -> str:
        if not self.detectadas:
            return "Ninguna request de escritura (POST/PUT/DELETE/PATCH) detectada."
        lineas = [f"⚠️  {len(self.detectadas)} request(s) de escritura detectada(s):"]
        for metodo, url in self.detectadas:
            lineas.append(f"    {metodo} {url}")
        return "\n".join(lineas)


async def login(page: Page):
    print("Iniciando sesión...")
    await page.goto(config.URL_LOGIN, timeout=config.TIMEOUT_NAV)
    await page.wait_for_selector("#username", timeout=config.TIMEOUT_ELEMENT)
    await page.fill("#username", config.USERNAME)
    await page.fill("#password", config.PASSWORD)
    await page.click("#login")
    await page.wait_for_selector("#userfullname", state="attached", timeout=config.TIMEOUT_ELEMENT)
    print("Sesión iniciada.")


async def buscar_proyecto(page: Page, proyecto_nombre: str):
    """Navega a Materiales y busca el proyecto. Deja la fila de resultado
    lista para clicar, pero NO clica nada todavía."""
    await page.goto(config.URL_MATERIALES, timeout=config.TIMEOUT_NAV)
    await page.wait_for_selector("#nombre", timeout=config.TIMEOUT_ELEMENT)
    await page.select_option("#estado_proyecto", value=["Material OK", "Sin Material"])
    await page.fill("#nombre", proyecto_nombre)
    await page.click("#find")
    await page.wait_for_selector("#tablaTree tbody tr", timeout=config.TIMEOUT_ELEMENT)


async def _fila_del_proyecto(page: Page, proyecto_nombre: str):
    rows = await page.locator("#tablaTree tbody tr").all()
    for row in rows:
        tds = await row.locator("td").all()
        if not tds:
            continue
        nombre = (await tds[0].inner_text()).strip().split("\n")[0].strip()
        if nombre == proyecto_nombre:
            return row
    return None


async def _listar_iconos_de_acciones(row) -> list:
    """Vuelca tag/title/src de todo lo clicable en la columna de Acciones,
    sin clicar nada. Sirve para confirmar el título real del ícono de
    edición antes de intentar abrirlo."""
    tds = await row.locator("td").all()
    acciones_td = tds[-1]
    imgs = await acciones_td.locator("img").all()
    info = []
    for img in imgs:
        title = await img.get_attribute("title")
        src = await img.get_attribute("src")
        info.append({"title": title, "src": src})
    return info


async def _describir_campo(page: Page, campo: str, mid: str, tipo: str) -> dict:
    """Para un campo de MATERIAL_ID_PATTERNS, resuelve su selector real y
    reporta existencia/tag/inner_text/input_value. Nunca escribe nada."""
    selector = _material_field_id(campo, mid, tipo)
    loc = page.locator(selector)
    count = await loc.count()
    if count == 0:
        return {"campo": campo, "id": selector, "existe": False}

    tag = await loc.first.evaluate("el => el.tagName")

    try:
        inner_text = (await loc.first.inner_text()).strip()
    except Exception as e:
        inner_text = f"<error: {e}>"

    valor_control = None
    if tag in ("INPUT", "TEXTAREA"):
        try:
            valor_control = await loc.first.input_value()
        except Exception as e:
            valor_control = f"<error: {e}>"
    elif tag == "SELECT":
        try:
            valor_control = await loc.first.evaluate(
                "el => el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : null"
            )
        except Exception as e:
            valor_control = f"<error: {e}>"

    return {
        "campo": campo,
        "id": selector,
        "existe": True,
        "tag": tag,
        "inner_text": inner_text,
        "valor_control": valor_control,
    }


async def _leer_hdn_ids(page: Page):
    hdn_items = await page.locator("#hdnItemsId").get_attribute("value")
    hdn_suministros = await page.locator("#hdnSuministrosId").get_attribute("value")
    item_ids = [x.strip() for x in hdn_items.split(",") if x.strip()] if hdn_items else []
    suministro_ids = [x.strip() for x in hdn_suministros.split(",") if x.strip()] if hdn_suministros else []
    return item_ids, suministro_ids


async def _volcar_vista(page: Page, proyecto_nombre: str, etiqueta: str) -> dict:
    """Vuelca HTML a disco y describe los 12 campos de MATERIAL_ID_PATTERNS
    para el primer item y el primer suministro disponibles. `etiqueta` es
    'detalle' o 'formulario', usada para nombrar los archivos."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    html = await page.content()
    nombre_archivo = f"dump_{etiqueta}_{proyecto_nombre.replace(' ', '_').replace('/', '-')}_{_ts()}.html"
    ruta = os.path.join(OUTPUT_DIR, nombre_archivo)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  HTML volcado en: {ruta}")

    try:
        item_ids, suministro_ids = await _leer_hdn_ids(page)
    except Exception as e:
        print(f"  ⚠️  No se pudieron leer #hdnItemsId/#hdnSuministrosId: {e}")
        return {"etiqueta": etiqueta, "hdn_presente": False, "campos": []}

    print(f"  #hdnItemsId: {item_ids}")
    print(f"  #hdnSuministrosId: {suministro_ids}")

    campos_reportados = []
    if item_ids:
        mid = item_ids[0]
        for campo, spec in MATERIAL_ID_PATTERNS.items():
            if "item" not in spec["tipos"]:
                continue
            campos_reportados.append(await _describir_campo(page, campo, mid, "item"))
    if suministro_ids:
        mid = suministro_ids[0]
        for campo, spec in MATERIAL_ID_PATTERNS.items():
            if "suministro" not in spec["tipos"]:
                continue
            campos_reportados.append(await _describir_campo(page, campo, mid, "suministro"))

    return {
        "etiqueta": etiqueta,
        "hdn_presente": True,
        "item_ids": item_ids,
        "suministro_ids": suministro_ids,
        "campos": campos_reportados,
    }


def _imprimir_tabla_campos(resultado: dict):
    print(f"\n  --- Campos vistos en '{resultado['etiqueta']}' ---")
    if not resultado.get("campos"):
        print("  (sin campos para reportar)")
        return
    header = f"  {'campo':<20} {'existe':<7} {'tag':<10} {'inner_text':<25} {'valor_control'}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for c in resultado["campos"]:
        if not c["existe"]:
            print(f"  {c['campo']:<20} {'NO':<7} {'-':<10} {'-':<25} -   (id={c['id']})")
            continue
        it = (c["inner_text"] or "")[:25]
        vc = c["valor_control"]
        print(f"  {c['campo']:<20} {'si':<7} {c['tag']:<10} {it:<25} {vc}")


async def explorar_proyecto_sano(page: Page, proyecto_nombre: str):
    print(f"\n{'=' * 70}\nProyecto de referencia (sano): {proyecto_nombre}\n{'=' * 70}")

    await buscar_proyecto(page, proyecto_nombre)
    row = await _fila_del_proyecto(page, proyecto_nombre)
    if row is None:
        print(f"⚠️  No se encontró fila para '{proyecto_nombre}'. Verificá el nombre exacto.")
        return

    iconos = await _listar_iconos_de_acciones(row)
    print(f"Íconos en la columna de Acciones: {iconos}")

    # --- Vista 1: Visualizar Detalle ---
    print(f"\n--- Abriendo '{TITULO_ICONO_DETALLE}' ---")
    monitor_detalle = MonitorEscrituras(page)
    btn_detalle = row.locator(f"img[title='{TITULO_ICONO_DETALLE}']").first
    await btn_detalle.click()
    await page.wait_for_selector("#detalleProyecto table", timeout=config.TIMEOUT_ELEMENT)
    resultado_detalle = await _volcar_vista(page, proyecto_nombre, "detalle")
    _imprimir_tabla_campos(resultado_detalle)
    print(f"  Red durante 'Visualizar Detalle': {monitor_detalle.reporte()}")

    # Salida limpia: goto fresco, nunca go_back() (riesgo de autosave al
    # abandonar una vista con inputs).
    await buscar_proyecto(page, proyecto_nombre)
    row = await _fila_del_proyecto(page, proyecto_nombre)
    if row is None:
        print(f"⚠️  No se volvió a encontrar la fila de '{proyecto_nombre}' tras recargar la búsqueda.")
        return

    # --- Vista 2: Editar Formulario ---
    print(f"\n--- Abriendo '{TITULO_ICONO_EDITAR}' ---")
    btn_editar = row.locator(f"img[title='{TITULO_ICONO_EDITAR}']").first
    if await btn_editar.count() == 0:
        print(
            f"⚠️  No se encontró ícono con title='{TITULO_ICONO_EDITAR}'. "
            f"Íconos disponibles: {iconos}. Ajustá TITULO_ICONO_EDITAR en este "
            f"script si el ERP usa otro texto."
        )
        return

    monitor_form = MonitorEscrituras(page)
    await btn_editar.click()
    # No sabemos a priori si el formulario usa el mismo selector
    # '#detalleProyecto table' que la vista de detalle. Se intenta primero
    # ese selector (lo más probable si comparten plantilla) y, si no
    # aparece, se cae a esperar por el texto visible en el encabezado de la
    # captura del usuario ("Item - Material"), que no depende de ids.
    try:
        await page.wait_for_selector("#detalleProyecto table", timeout=config.TIMEOUT_ELEMENT)
    except Exception:
        print("  '#detalleProyecto table' no apareció, probando por el texto del encabezado...")
        await page.get_by_text("Item - Material").wait_for(timeout=config.TIMEOUT_ELEMENT)

    resultado_form = await _volcar_vista(page, proyecto_nombre, "formulario")
    _imprimir_tabla_campos(resultado_form)
    print(f"  Red durante 'Editar Formulario': {monitor_form.reporte()}")

    # --- Comparación campo a campo ---
    print(f"\n--- Comparación detalle vs. formulario ---")
    campos_detalle = {c["campo"]: c for c in resultado_detalle.get("campos", [])}
    campos_form = {c["campo"]: c for c in resultado_form.get("campos", [])}
    for campo in campos_detalle.keys() | campos_form.keys():
        d = campos_detalle.get(campo)
        f = campos_form.get(campo)
        d_tag = d["tag"] if d and d.get("existe") else "NO EXISTE"
        f_tag = f["tag"] if f and f.get("existe") else "NO EXISTE"
        marca = "  " if d_tag == f_tag else "⚠️"
        print(f"  {marca} {campo:<20} detalle={d_tag:<10} formulario={f_tag}")

    # Salida limpia otra vez, para no dejar el navegador sobre un formulario.
    await buscar_proyecto(page, proyecto_nombre)


async def explorar_proyecto_roto(page: Page, proyecto_nombre: str):
    print(f"\n{'=' * 70}\nProyecto roto: {proyecto_nombre}\n{'=' * 70}")

    try:
        await buscar_proyecto(page, proyecto_nombre)
    except Exception as e:
        print(f"⚠️  No se encontró/cargó la búsqueda de materiales para '{proyecto_nombre}': {e}")
        return

    row = await _fila_del_proyecto(page, proyecto_nombre)
    if row is None:
        print(f"⚠️  No se encontró fila para '{proyecto_nombre}'.")
        return

    iconos = await _listar_iconos_de_acciones(row)
    print(f"Íconos en la columna de Acciones: {iconos}")

    btn_editar = row.locator(f"img[title='{TITULO_ICONO_EDITAR}']").first
    if await btn_editar.count() == 0:
        print(f"⚠️  No se encontró ícono '{TITULO_ICONO_EDITAR}'. Íconos disponibles: {iconos}")
        return

    monitor_form = MonitorEscrituras(page)
    await btn_editar.click()
    try:
        try:
            await page.wait_for_selector("#detalleProyecto table", timeout=config.TIMEOUT_ELEMENT)
        except Exception:
            await page.get_by_text("Item - Material").wait_for(timeout=config.TIMEOUT_ELEMENT)
        print(f"✅ 'Editar Formulario' CARGÓ para '{proyecto_nombre}'.")
        resultado = await _volcar_vista(page, proyecto_nombre, "formulario_roto")
        _imprimir_tabla_campos(resultado)
    except Exception as e:
        print(f"❌ 'Editar Formulario' TAMPOCO cargó para '{proyecto_nombre}': {e}")
    print(f"  Red durante el intento: {monitor_form.reporte()}")

    # Salida limpia.
    try:
        await buscar_proyecto(page, proyecto_nombre)
    except Exception:
        pass


async def main(proyecto_sano: Optional[str], solo_rotos: bool):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("Iniciando Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = await context.new_page()
        try:
            await login(page)

            if not solo_rotos:
                await explorar_proyecto_sano(page, proyecto_sano or PROYECTO_SANO_DEFAULT)

            for proyecto in PROYECTOS_ROTOS:
                await explorar_proyecto_roto(page, proyecto)

        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

    print(f"\nListo. Volcados HTML en: {OUTPUT_DIR}")
    print(
        "Recordatorio Fase 2: verificar a mano en la UI que ninguno de los "
        "proyectos tocados haya cambiado de valores tras correr este script."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--proyecto-sano", default=None,
        help=f"Proyecto de referencia para comparar ambas vistas (default: {PROYECTO_SANO_DEFAULT}).",
    )
    parser.add_argument(
        "--solo-rotos", action="store_true",
        help="Saltea la comparación del proyecto sano y solo prueba los 2 proyectos rotos.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.proyecto_sano, args.solo_rotos))
