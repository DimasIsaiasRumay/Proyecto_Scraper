"""
Script de exploración manual (NO es parte de un test suite automatizado).

Golpea el ERP de PRODUCCIÓN en vivo con las credenciales reales. Navega,
imprime el HTML de la primera fila de proyecto/material encontrada — útil
para inspeccionar la estructura del DOM cuando cambia algo en el ERP.
No lo ejecute pytest/CI automáticamente.
"""
import os
import sys
import asyncio
from playwright.async_api import async_playwright

sys.path.append(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scraper-fabricacion")))
import config

async def main():
    print("Iniciando Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Usar un viewport grande para evitar elementos ocultos (mobile view)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            print("Paso 1: Iniciando sesión...")
            await page.goto(config.URL_LOGIN, timeout=config.TIMEOUT_NAV)
            await page.wait_for_selector("#username", timeout=config.TIMEOUT_ELEMENT)
            await page.fill("#username", config.USERNAME)
            await page.fill("#password", config.PASSWORD)
            await page.click("#login")

            # Esperar a que se cargue la sesión
            await page.wait_for_selector("#userfullname", state="attached", timeout=config.TIMEOUT_ELEMENT)
            print("Login exitoso.")

            print("Paso 2: Navegando a Proyectos para buscar un proyecto real...")
            await page.goto(config.URL_PROYECTOS, timeout=config.TIMEOUT_NAV)
            await page.wait_for_selector("#tablaTree", timeout=config.TIMEOUT_ELEMENT)

            # Clicar en Buscar para cargar proyectos
            await page.click("#find")
            # Esperar a que aparezcan filas en la tabla
            await page.wait_for_selector("#proyectos tr", timeout=config.TIMEOUT_ELEMENT)

            # Obtener el primer proyecto
            rows = await page.locator("#proyectos tr").all()
            print(f"Total filas encontradas en proyectos: {len(rows)}")

            first_project_name = None
            for row in rows:
                parent_id = await row.get_attribute("data-tt-parent-id")
                if not parent_id:  # Fila raíz (Proyecto)
                    tds = await row.locator("td").all()
                    if tds:
                        td1_text = await tds[0].inner_text()
                        first_project_name = td1_text.strip().split("\n")[0].strip()
                        print(f"Primer proyecto encontrado: '{first_project_name}'")
                        print(f"HTML de la fila del proyecto: {await row.inner_html()}")
                        break

            if not first_project_name:
                print("No se encontraron proyectos raíz.")
                return

            print(f"Paso 3: Navegando a Materiales para buscar '{first_project_name}'...")
            await page.goto(config.URL_MATERIALES, timeout=config.TIMEOUT_NAV)
            await page.wait_for_selector("#nombre", timeout=config.TIMEOUT_ELEMENT)

            # Llenar la búsqueda
            await page.fill("#nombre", first_project_name)
            await page.click("#find")

            # Esperar que la tabla cargue filas
            await page.wait_for_selector("#tablaTree tbody tr", timeout=config.TIMEOUT_ELEMENT)

            # Ver qué filas hay en la tabla de materiales
            mat_rows = await page.locator("#tablaTree tbody tr").all()
            print(f"Filas encontradas en tabla de búsqueda de materiales: {len(mat_rows)}")

            # Dump de la primera fila y sus acciones
            for row in mat_rows:
                tds = await row.locator("td").all()
                if tds:
                    td1_text = await tds[0].inner_text()
                    clean_name = td1_text.strip().split("\n")[0].strip()
                    print(f"Fila encontrada en materiales: '{clean_name}'")
                    # Acciones col is the last col (usually td[6])
                    actions_td = tds[-1]
                    print(f"HTML de columna de acciones: {await actions_td.inner_html()}")

                    # Intentar encontrar un botón o enlace para hacer clic
                    click_target = actions_td.locator("img[title='Visualizar Detalle']").first
                    if await click_target.count() > 0:
                        print("Click en Visualizar Detalle...")
                        await click_target.click()

                        # Esperar a que aparezca la sección de detalles
                        print("Esperando tabla de detalleProyecto...")
                        await page.wait_for_selector("#detalleProyecto table", timeout=15000)
                        print("Tabla de detalleProyecto encontrada.")

                        # Buscar una fila de item y mostrar su HTML completo
                        rows = await page.locator("#detalleProyecto tr").all()
                        for row in rows:
                            html = await row.inner_html()
                            if "cant_" in html:
                                print(f"HTML Completo de la fila: <tr>{html}</tr>")
                                break
                    break

        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
