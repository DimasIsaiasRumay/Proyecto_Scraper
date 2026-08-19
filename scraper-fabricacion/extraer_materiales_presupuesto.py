import os
import sys
import sqlite3
import json
import logging
from datetime import datetime
from playwright.sync_api import sync_playwright

# Add current folder to path to import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
from scraper import setup_logger, login, human_delay, parse_float
from database import init_db, upsert_producto_material

# Setup a clean logger specifically for this budget scraper
logger = setup_logger()

def load_db_projects_products(conn):
    """Loads all unique project-product combinations registered in the database."""
    c = conn.cursor()
    c.execute("SELECT DISTINCT proyecto_nombre, nombre FROM proyecto_productos")
    rows = c.fetchall()
    
    db_set = set()
    for proj, prod in rows:
        db_set.add((proj.strip().lower(), prod.strip().lower()))
    return db_set, rows

def scrape_budget_materials():
    logger.info("==================================================")
    logger.info("INICIANDO EXTRACCIÓN DE MATERIALES DE PRESUPUESTO")
    logger.info("==================================================")
    
    # 1. Initialize SQLite Database
    logger.info(f"Conectando a base de datos en: {config.DB_PATH}")
    conn = init_db(config.DB_PATH)
    db_set, raw_db_rows = load_db_projects_products(conn)
    logger.info(f"Se cargaron {len(db_set)} combinaciones de Proyecto-Producto de la base de datos.")
    
    if not db_set:
        logger.warning("No hay productos registrados en la base de datos para procesar. Abortando.")
        conn.close()
        return

    # 2. Run Playwright
    logger.info("Iniciando navegador Chromium...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=config.HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = context.new_page()
        
        try:
            # Login
            login(page)
            
            # Navigate to budget page
            url = config.URL_PRESUPUESTO
            logger.info(f"Navegando a presupuestos: {url}")
            page.goto(url, timeout=config.TIMEOUT_NAV)
            human_delay(2, 3)
            
            # Select filters
            logger.info("Colocando filtros en selectores...")
            page.select_option("#estado_proyecto", value=["Material OK", "Sin Material"])
            human_delay(0.5, 1.0)
            page.select_option("#estado_asignacion", value=["SI"]) # 'SI' is 'Asignados'
            human_delay(0.5, 1.0)
            page.select_option("#estado_presupuesto", value=["ALL"]) # 'ALL' is '-- Todos --'
            human_delay(0.5, 1.0)
            
            # Click find
            logger.info("Haciendo clic en 'Buscar'...")
            page.click("#find")
            
            # Esperar a que el listado TERMINE de cargar.
            #
            # Antes acá había un human_delay(15.0, 15.0) fijo. El problema: la
            # tabla trae ~14.000 filas (medido en vivo el 19/08/2026), así que
            # si algún día la carga tarda 16s en vez de 15, el page.evaluate()
            # de más abajo devuelve 0 filas, los ~134 combos dan MISS y el
            # script igual termina logueando "Extracción finalizada con éxito"
            # — falla silenciosa.
            #
            # Tampoco sirve wait_for_selector(), ni con state="attached" (ambas
            # variantes probadas en vivo el 19/08/2026: las dos agotan el
            # timeout aunque las filas YA estén en el DOM). El motivo está en
            # los tiempos de la corrida que sí funcionaba: el page.evaluate()
            # de la extracción tardaba 17,8s en devolver, cuando un
            # querySelectorAll sobre 14.000 filas se resuelve en milisegundos.
            # Eso indica que el hilo principal del navegador queda bloqueado
            # renderizando el treetable — y wait_for_selector hace su polling
            # DENTRO de la página, así que esos callbacks nunca llegan a
            # correr y agota el timeout sin poder comprobar nada. El sleep
            # ciego "funcionaba" justamente porque no dependía del hilo.
            #
            # Por eso se sondea con page.evaluate(): misma primitiva que usa
            # la extracción de más abajo, que sí se encola y devuelve cuando
            # el hilo se libera. Se espera a que el conteo se estabilice, que
            # es la señal real de "terminó de renderizar".
            logger.info("Esperando que cargue el listado...")
            ESPERA_MAX_SEGUNDOS = 120
            SONDEOS_ESTABLES_REQUERIDOS = 3
            filas_previas = -1
            sondeos_estables = 0
            inicio_espera = datetime.now()
            while (datetime.now() - inicio_espera).total_seconds() < ESPERA_MAX_SEGUNDOS:
                filas_actuales = page.evaluate(
                    "() => document.querySelectorAll('#tablaTree tbody tr').length"
                )
                # Un conteo de 0 estable NO es "terminó de cargar" sino "no
                # cargó todavía" (o no cargó nunca): se sigue sondeando hasta
                # el tope, y si nunca aparece nada se aborta más abajo.
                if filas_actuales == filas_previas and filas_actuales > 0:
                    sondeos_estables += 1
                    if sondeos_estables >= SONDEOS_ESTABLES_REQUERIDOS:
                        break
                else:
                    sondeos_estables = 0
                    filas_previas = filas_actuales
                human_delay(1.0, 1.0)
            else:
                if filas_previas > 0:
                    logger.warning(
                        f"El listado siguió creciendo tras {ESPERA_MAX_SEGUNDOS}s "
                        f"({filas_previas} filas hasta ahora). Se continúa igual, pero el "
                        f"resultado podría estar incompleto."
                    )

            if filas_previas <= 0:
                logger.error(
                    f"El listado de presupuesto no devolvió ninguna fila tras "
                    f"{ESPERA_MAX_SEGUNDOS}s. Se aborta sin guardar nada, en vez de seguir "
                    f"y reportar 0 coincidencias como si fuera una corrida exitosa."
                )
                return

            logger.info(f"Listado estabilizado en {filas_previas} filas.")

            logger.info("Extrayendo datos de la tabla mediante evaluación JS (Optimizado)...")
            rows_data = page.evaluate("""() => {
                const rows = Array.from(document.querySelectorAll('#tablaTree tbody tr'));
                return rows.map(row => {
                    const tds = Array.from(row.querySelectorAll('td'));
                    return {
                        id: row.getAttribute('data-tt-id'),
                        parentId: row.getAttribute('data-tt-parent-id'),
                        className: row.className,
                        texts: tds.map(td => td.innerText.trim())
                    };
                });
            }""")
            
            logger.info(f"Se extrajeron {len(rows_data)} filas del DOM.")

            # Guarda contra la falla silenciosa: si no se extrajo nada, no
            # tiene sentido seguir — el emparejamiento daría 0 MATCH / 134
            # MISS y el script terminaría con "✅ finalizada con éxito",
            # pisando además el JSON de salida con una lista vacía.
            if not rows_data:
                logger.error(
                    "No se extrajo ninguna fila del listado de presupuesto. Se aborta "
                    "sin tocar la base ni el JSON, para no reemplazar datos buenos por vacío."
                )
                return

            # 3. Parse hierarchy
            logger.info("Estructurando árbol jerárquico de proyectos y productos...")
            current_project = None
            current_product = None
            parsed_projects = {}
            
            for row in rows_data:
                tt_id = row["id"]
                tt_parent_id = row["parentId"]
                td_texts = row["texts"]
                
                if not td_texts:
                    continue
                    
                td0_text = td_texts[0]
                
                if not tt_parent_id:
                    # Level 1: Project row
                    project_name = td0_text.split("\n")[0].strip()
                    current_project = {
                        "id": tt_id,
                        "name": project_name,
                        "products": {}
                    }
                    parsed_projects[project_name] = current_project
                    current_product = None
                else:
                    if current_project and tt_parent_id == current_project["id"]:
                        # Level 2: Product row
                        product_name = td0_text
                        current_product = {
                            "id": tt_id,
                            "name": product_name,
                            "materials": []
                        }
                        current_project["products"][product_name] = current_product
                    elif current_product and tt_parent_id == current_product["id"]:
                        # Level 3: Material row
                        desc = td0_text
                        is_suministro = desc.startswith("(S)")
                        if is_suministro:
                            desc = desc[3:].strip()
                            
                        mat_text = td_texts[1] if len(td_texts) > 1 else ""
                        if " - " in mat_text:
                            parts = mat_text.split(" - ", 1)
                            codigo_mp = parts[0].strip()
                            mat_desc = parts[1].strip()
                        else:
                            codigo_mp = "N/A"
                            mat_desc = mat_text
                            
                        if is_suministro:
                            lp = None
                            a = None
                            c = td_texts[3] if len(td_texts) > 3 else ""
                        else:
                            lp = td_texts[2] if len(td_texts) > 2 else ""
                            a = td_texts[3] if len(td_texts) > 3 else ""
                            c = td_texts[4] if len(td_texts) > 4 else ""
                            
                        material_data = {
                            "tipo": "suministro" if is_suministro else "item",
                            "descripcion": desc,
                            "codigo_mp": codigo_mp,
                            "material_descripcion": mat_desc,
                            "l_p": parse_float(lp),
                            "a": parse_float(a),
                            "c": parse_float(c)
                        }
                        current_product["materials"].append(material_data)
            
            logger.info(f"Estructuración completada. Se encontraron {len(parsed_projects)} proyectos raíz.")
            
            # 4. Matching & Saving
            logger.info("Emparejando datos extraídos con registros de la base de datos...")
            matches_count = 0
            misses_count = 0
            
            json_output = []
            
            for db_proj, db_prod in raw_db_rows:
                proj_key_db = db_proj.strip().lower()
                prod_key_db = db_prod.strip().lower()
                
                matched = False
                for parsed_proj_name, parsed_proj in parsed_projects.items():
                    norm_db_proj = proj_key_db.replace(" ", "").replace("_", "")
                    norm_parsed_proj = parsed_proj_name.strip().lower().replace(" ", "").replace("_", "")
                    
                    if norm_db_proj == norm_parsed_proj or norm_db_proj in norm_parsed_proj or norm_parsed_proj in norm_db_proj:
                        for parsed_prod_name, parsed_prod in parsed_proj["products"].items():
                            norm_db_prod = prod_key_db.replace(" ", "").replace("_", "")
                            norm_parsed_prod = parsed_prod_name.strip().lower().replace(" ", "").replace("_", "")
                            
                            if norm_db_prod == norm_parsed_prod:
                                matched = True
                                matches_count += 1
                                
                                logger.info(f"MATCH: {db_proj} -> {db_prod} ({len(parsed_prod['materials'])} materiales)")
                                
                                # Save in SQLite and append to JSON list
                                for mat in parsed_prod["materials"]:
                                    # Insert/Update in database
                                    db_mat_data = {
                                        "proyecto_nombre": db_proj, # Use the official DB name
                                        "producto_nombre": db_prod, # Use the official DB name
                                        "tipo": mat["tipo"],
                                        "nombre": mat["descripcion"],
                                        "codigo_mp": mat["codigo_mp"],
                                        "descripcion_material": mat["material_descripcion"],
                                        "l_p": mat["l_p"],
                                        "a": mat["a"],
                                        "c": mat["c"]
                                    }
                                    upsert_producto_material(conn, db_mat_data)
                                
                                # Add to JSON output structure
                                json_output.append({
                                    "proyecto_nombre": db_proj,
                                    "producto_nombre": db_prod,
                                    "materiales": parsed_prod["materials"]
                                })
                                break
                        if matched:
                            break
                            
                if not matched:
                    misses_count += 1
                    logger.warning(f"MISS: No se encontró en el presupuesto: {db_proj} -> {db_prod}")
            
            # Save JSON File
            json_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
            os.makedirs(json_dir, exist_ok=True)
            json_path = os.path.join(json_dir, "materiales_productos.json")
            
            with open(json_path, "w", encoding="utf-8") as jf:
                json.dump(json_output, jf, indent=4, ensure_ascii=False)
                
            logger.info(f"✅ Extracción finalizada con éxito.")
            logger.info(f"   Coincidencias guardadas en SQLite y JSON: {matches_count}")
            logger.info(f"   Registros no encontrados (Dummy/Test): {misses_count}")
            logger.info(f"   Archivo JSON guardado en: {json_path}")
            
        except Exception as e:
            logger.error(f"Error durante el proceso de extracción: {e}", exc_info=True)
        finally:
            conn.close()
            browser.close()

if __name__ == "__main__":
    scrape_budget_materials()
