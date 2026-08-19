"""
Script de validación manual — Fase 6 de docs/plan_fallback_formulario.md.

Desviación documentada del plan original: en vez de un flag
--dry-run-formulario threadeado por todo el loop de main.py (que tocaría el
entrypoint de producción — upsert_proyecto/upsert_item, checkpoints, lock,
etc. — solo para poder saltear el upsert de materiales), este script llama
DIRECTO a las mismas funciones de producción (scraper.login,
scraper.extraer_materiales) sobre uno o más proyectos puntuales. Es un
dry-run más fiel, no menos: ejercita exactamente el mismo código que corre
en una ejecución real (incluido el fallback a "Editar Formulario" de
scraper.py:_intentar_fallback_formulario y el monitor de escrituras de
_MonitorEscriturasFormulario), pero sin importar database.py en ningún
momento — no hay forma de que este script escriba nada en la BD aunque
quisiera.

Uso:
    python validar_extraccion_formulario.py
    python validar_extraccion_formulario.py --proyecto "OTRO_NOMBRE"

Por default corre sobre los 2 proyectos que hoy fallan con "Visualizar
Detalle" (ver docs/plan_fallback_formulario.md):
    - OP-ING-EPLIQ-070826-0001
    - OP_CLARO_Complemento COWRoja_2906261616

Después de correrlo, comparar cada valor impreso contra lo que se ve a mano
en la UI del ERP para esos mismos proyectos — campo por campo, no solo
"aparecieron materiales sí/no". El criterio de rechazo de la Fase 6: si
algún campo numérico llega vacío o en 0 cuando la UI muestra un valor
real, el fallback NO pasa la validación.

No lo ejecute pytest/CI automáticamente.
"""
import argparse
import os
import sys

sys.path.append(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scraper-fabricacion")))
import config
from playwright.sync_api import sync_playwright

# Se importan las funciones REALES de producción, no una reimplementación —
# el objetivo es validar exactamente lo que va a correr en una corrida real.
from scraper import setup_logger, login, extraer_materiales

PROYECTOS_DEFAULT = [
    "OP-ING-EPLIQ-070826-0001",
    "OP_CLARO_Complemento COWRoja_2906261616",
]


def _imprimir_material(m) -> None:
    print(f"  [{m.tipo:10}] {m.codigo_mp:14} {m.descripcion[:45]}")
    print(
        f"      cantidad={m.cantidad!r}  desperdicio_12={m.desperdicio_12!r}  "
        f"validacion_diseno={m.validacion_diseno!r}"
    )
    print(f"      stock_chapa_barras={m.stock_chapa_barras!r}  comprar={m.comprar!r}")
    print(f"      precio_sw={m.precio_sw!r}  precio_compra={m.precio_compra!r}")
    print(f"      orden_compra={m.orden_compra!r}  numero_factura={m.numero_factura!r}")
    print(f"      estado_compra={m.estado_compra!r}")
    print(f"      comentarios={m.comentarios!r}")
    print(f"      proveedor={m.proveedor!r}")


def main(proyectos):
    setup_logger()
    print("Iniciando Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=config.HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()
        try:
            login(page)
            for proyecto_nombre in proyectos:
                print(f"\n{'=' * 70}\n{proyecto_nombre}\n{'=' * 70}")
                try:
                    materiales = extraer_materiales(page, proyecto_nombre)
                except Exception as e:
                    print(f"ERROR extrayendo '{proyecto_nombre}': {e}")
                    continue
                print(f"{len(materiales)} material(es) extraídos (NO se guardó nada en la BD):")
                for m in materiales:
                    _imprimir_material(m)
        finally:
            browser.close()

    print(
        "\nListo. Comparar cada valor de arriba contra la UI del ERP a mano, "
        "campo por campo (no solo 'aparecieron materiales sí/no'), antes de "
        "confiar en el fallback en una corrida real. Ver criterio de rechazo "
        "en la Fase 6 de docs/plan_fallback_formulario.md."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--proyecto", action="append", default=None,
        help="Nombre exacto de un proyecto a validar. Repetible. Default: los 2 proyectos rotos conocidos.",
    )
    args = parser.parse_args()
    main(args.proyecto or PROYECTOS_DEFAULT)
