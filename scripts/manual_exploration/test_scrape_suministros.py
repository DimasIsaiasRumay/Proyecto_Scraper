"""
Script de exploración manual (NO es parte de un test suite automatizado).

Golpea el ERP de PRODUCCIÓN en vivo. Vuelca los IDs de DOM reales alrededor
de un suministro de un proyecto específico — útil para verificar los
patrones de selector (#suministro_cant_{id}, etc.) usados en scraper.py
cuando el ERP cambia algo. No lo ejecute pytest/CI automáticamente.
"""
import argparse
import os
import sqlite3
import sys
import asyncio
from playwright.async_api import async_playwright

sys.path.append(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scraper-fabricacion")))
import config


def elegir_proyecto_por_defecto() -> str:
    """
    Toma el proyecto sincronizado más recientemente de la BD local del
    scraper, en vez de depender de un nombre de proyecto hardcodeado en el
    código (que queda desactualizado en cuanto ese proyecto puntual deja de
    existir o se renombra en el ERP — la búsqueda simplemente no encuentra
    filas, sin ningún aviso de que el nombre ya no es válido).
    """
    db_path = os.path.join(config.BASE_DIR, "data", "fabricacion.db")
    if not os.path.exists(db_path):
        raise RuntimeError(
            f"BD no encontrada en {db_path}. Corré el scraper al menos una "
            f"vez antes de usar este script, o pasá un proyecto explícito "
            f"con --proyecto."
        )
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT nombre FROM proyectos ORDER BY fecha_ultima_sync DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise RuntimeError(
            "La tabla 'proyectos' está vacía. Pasá un proyecto explícito con --proyecto."
        )
    return row[0]


async def main(proyecto_nombre: str):
    print("Iniciando Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            print("Iniciando sesión...")
            await page.goto(config.URL_LOGIN, timeout=config.TIMEOUT_NAV)
            await page.wait_for_selector("#username", timeout=config.TIMEOUT_ELEMENT)
            await page.fill("#username", config.USERNAME)
            await page.fill("#password", config.PASSWORD)
            await page.click("#login")
            await page.wait_for_selector("#userfullname", state="attached", timeout=config.TIMEOUT_ELEMENT)

            print("Navegando a Materiales...")
            await page.goto(config.URL_MATERIALES, timeout=config.TIMEOUT_NAV)
            await page.wait_for_selector("#nombre", timeout=config.TIMEOUT_ELEMENT)

            print(f"Buscando proyecto: {proyecto_nombre}")
            await page.fill("#nombre", proyecto_nombre)
            await page.click("#find")
            try:
                await page.wait_for_selector("#tablaTree tbody tr", timeout=config.TIMEOUT_ELEMENT)
            except Exception:
                print(
                    f"No se encontraron filas para '{proyecto_nombre}'. Si el "
                    f"nombre vino de la BD local (--proyecto no especificado), "
                    f"puede que ya no exista en el ERP o que su estado esté "
                    f"filtrado en esta pantalla. Probá con --proyecto \"OTRO_NOMBRE\"."
                )
                return

            # Clicar en Visualizar Detalle
            preview_btn = page.locator("img[title='Visualizar Detalle']").first
            await preview_btn.click()

            print("Esperando tabla de detalleProyecto...")
            await page.wait_for_selector("#detalleProyecto table", timeout=15000)

            # Obtener el hdnSuministrosId
            hdn_suministros = await page.locator("#hdnSuministrosId").get_attribute("value")
            suministro_ids = [x.strip() for x in hdn_suministros.split(",") if x.strip()] if hdn_suministros else []
            print(f"Suministros IDs: {suministro_ids}")

            if suministro_ids:
                first_sum_id = suministro_ids[0]
                print(f"Buscando elementos con el ID {first_sum_id}...")

                # Buscar cualquier elemento que termine con o contenga el primer ID de suministro
                # de forma que nos revele los prefijos reales de las columnas en Suministros
                elements = await page.locator(f"[id*='_{first_sum_id}']").all()
                print(f"Se encontraron {len(elements)} elementos para el ID {first_sum_id}:")
                for el in elements:
                    el_id = await el.get_attribute("id")
                    el_tag = await el.evaluate("el => el.tagName")
                    el_text = await el.inner_text()
                    print(f"Tag: {el_tag} | ID: {el_id} | Text: {el_text[:100]}")

                # Mostrar también el HTML de la fila completa que contenga al primer ID de suministro
                sum_row = page.locator(f"tr:has([id*='_{first_sum_id}'])").first
                if await sum_row.count() > 0:
                    print(f"HTML Completo de fila de Suministro: <tr>{await sum_row.inner_html()}</tr>")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--proyecto", default=None,
        help="Nombre exacto del proyecto a explorar. Si se omite, se toma el "
             "sincronizado más recientemente de la BD local.",
    )
    args = parser.parse_args()

    if args.proyecto:
        _proyecto = args.proyecto
    else:
        try:
            _proyecto = elegir_proyecto_por_defecto()
        except RuntimeError as e:
            print(f"Error: {e}")
            sys.exit(1)

    asyncio.run(main(_proyecto))
