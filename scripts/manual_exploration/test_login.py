"""
Script de exploración manual (NO es parte de un test suite automatizado).

Golpea el ERP de PRODUCCIÓN en vivo con las credenciales reales de
scraper-fabricacion/.env. Ejecutar solo a mano cuando se necesite verificar el login.
No lo ejecute pytest/CI automáticamente: por eso vive en scripts/manual_exploration/
y no en un directorio "test/".
"""
import os
import sys
import asyncio
from playwright.async_api import async_playwright

# Ruta al módulo del scraper resuelta relativa a este archivo (portable entre máquinas).
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scraper-fabricacion")))

import config

async def test():
    print("Iniciando prueba de conexión con Playwright...")
    print(f"URL: {config.URL_LOGIN}")
    print(f"Usuario: {config.USERNAME}")

    async with async_playwright() as p:
        # Modo stealth y user agent
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            print("Navegando a la página de login...")
            await page.goto(config.URL_LOGIN, timeout=config.TIMEOUT_NAV)
            print("Página de login cargada.")

            # Verificar si ya estamos logueados o necesitamos loguear
            username_input = await page.wait_for_selector("#username", timeout=5000)
            if username_input:
                print("Llenando formulario de login...")
                await page.fill("#username", config.USERNAME)
                await page.fill("#password", config.PASSWORD)
                print("Haciendo click en Sign In...")
                await page.click("#login")

            print("Esperando redirección...")
            # Esperar a que cargue el nombre de usuario
            await page.wait_for_selector("#userfullname", timeout=15000)
            user_full_name = await page.inner_text("#userfullname")
            print(f"Login exitoso! Bienvenido: {user_full_name}")

            print("Navegando a Proyectos...")
            await page.goto(config.URL_PROYECTOS, timeout=config.TIMEOUT_NAV)
            await page.wait_for_selector("#find", timeout=10000)
            print("Página de proyectos cargada correctamente.")

        except Exception as e:
            print(f"Ocurrió un error durante la prueba: {e}")
            # Si hay error de msg en la página de login, capturarlo
            try:
                msg = await page.inner_text("#msg")
                if msg:
                    print(f"Mensaje de error en la página: {msg}")
            except Exception:
                pass
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
