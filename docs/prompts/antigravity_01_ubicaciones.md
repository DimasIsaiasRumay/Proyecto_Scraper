# Prompt para Antigravity — Iteración 1: Ubicaciones de Producción en Odoo

Copiar todo lo que sigue como instrucción de trabajo.

---

## Contexto

Repo: `C:\Users\Usuario\Desktop\Proyecto Scraper` (git, rama actual `main`).
Es un bot Playwright que scrapea un ERP de fabricación a SQLite
(`scraper-fabricacion/data/fabricacion.db`) y después sincroniza con Odoo 19 vía
la API JSON-2 (`odoo-integration/`).

Hoy la sincronización crea `project.project` + `project.task`. **Se reemplaza**
por la creación de ubicaciones virtuales de producción (`stock.location`), una por
proyecto de la última corrida del bot.

## Documento que manda

`docs/plan_stock_locations.md` es el contrato. **Leerlo completo antes de escribir
una línea de código.** Contiene, por fase: archivos exactos, firmas exactas,
dominios de búsqueda exactos, SQL exacto, formato exacto de los logs, lista de
tests con nombre y aserción, y criterios de aceptación con valores numéricos
reales medidos contra el sistema en producción el 18/08/2026.

No hay que rediseñar nada. Si algo del plan resulta imposible o incorrecto al
implementarlo: **detenerse, documentarlo en el reporte y preguntar.** No improvisar
una alternativa en silencio.

## Alcance de esta iteración

Fases **0 a 8** del plan, en ese orden exacto: `0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8`.

**La Fase 9 (corrida real que crea registros en Odoo) NO se ejecuta.** Al terminar
la Fase 8 hay que detenerse y esperar verificación.

## Reglas duras

1. **Rama:** `git checkout -b feat/ubicaciones-produccion` desde `main`. Nunca commitear en `main`. **Nunca `git push`.**
2. **Un commit por fase**, mensaje en español, formato `<tipo>(<ámbito>): <qué> (Fase N)`. Los mensajes exactos sugeridos están al pie de cada fase del plan. Sin `Co-Authored-By`.
3. **Odoo en esta iteración es solo lectura.** Permitido: `search_read`, `search`, `fields_get`. **Prohibido: `create`, `write`, `unlink`** contra el Odoo real, en cualquier fase de la 0 a la 8. El `--dry-run` de la Fase 6 no debe escribir ni en Odoo ni en la BD local.
4. **No tocar los datos del sistema viejo:** los 81 `project.project` y 131 `project.task` ya cargados quedan intactos. No borrar la columna `odoo_id` ni las 3378 filas de `odoo_sync_log`.
5. **Credenciales:** no abrir, modificar ni imprimir `odoo-integration/.env` ni `scraper-fabricacion/.env`. Nunca imprimir ni pegar en el reporte `ODOO_URL`, `ODOO_DATABASE`, `ODOO_API_KEY` ni el usuario del ERP. Para verificar que están cargadas, imprimir solo el largo (`len`).
6. **Archivos que se pueden tocar** (ninguno más):
   - `odoo-integration/database_reader.py`
   - `odoo-integration/odoo_models.py`
   - `odoo-integration/odoo_sync.py`
   - `odoo-integration/sync_locations.py` (nuevo)
   - `odoo-integration/sync_projects.py`, `odoo-integration/sync_tasks.py` (se borran con `git rm`)
   - `scraper-fabricacion/main.py` — **una sola línea**, la 416, más un comentario
   - `scripts/manual_exploration/explorar_ubicaciones_odoo.py` (nuevo)
   - `tests/test_odoo_locations.py`, `tests/test_run_selection.py` (nuevos)
   - `tests/test_odoo_builders.py` (se borra)
   - `README.md`, `docs/plan_stock_locations.md`, `docs/fase1_recon_ubicaciones.md` (nuevo), `docs/reporte_antigravity_01.md` (nuevo)

   No tocar: `odoo_client.py`, `sync_logger.py`, `common/`, el resto de `scraper-fabricacion/`, `tests/test_models.py`, `tests/test_parsing.py`, `tests/conftest.py`, `.github/`, `.gitignore`.
7. **Estilo:** seguir el del repo — comentarios y docstrings en español, mensajes de log con emoji e indentación de 2 espacios como en `sync_projects.py`, type hints en las firmas públicas. Los comentarios explican **por qué**, no **qué**.
8. **Python de referencia:** 3.10. Los tests tienen que pasar además en 3.12 y 3.13 (matriz de la CI) y **sin `.env` presente**.
9. No agregar dependencias nuevas. No agregar herramientas de formateo ni reordenar imports de archivos que el plan no lista.

## Definición de terminado

Al cerrar la Fase 8, entregar `docs/reporte_antigravity_01.md` con, en este orden:

1. **Por fase (0 a 8):** qué se hizo, hash del commit, y el criterio de aceptación del plan con el resultado **real** obtenido (no "OK": el número o la salida).
2. **Salidas completas y sin editar** de:
   ```bash
   python -m pytest -q
   ```
   ```bash
   git log --oneline main..feat/ubicaciones-produccion
   ```
   ```bash
   git diff --stat main..feat/ubicaciones-produccion
   ```
   ```bash
   cd odoo-integration && python odoo_sync.py --dry-run
   ```
   ```bash
   cd odoo-integration && python odoo_sync.py --help
   ```
3. **Pruebas de limpieza** (salida cruda de cada `grep`; se espera vacío):
   ```bash
   grep -rn "sync_projects\|sync_tasks" --include=*.py .
   ```
   ```bash
   grep -rn "get_all_projects\|get_productos\|get_producto_count\|save_producto_odoo_id\|get_all_projects_typed\|ProductoLocal" --include=*.py .
   ```
4. **Prueba de que el dry-run no escribió**: el comando de conteo de la Fase 6 del plan, corrido **antes y después** del `--dry-run`, con los dos resultados (se esperan iguales: `0` proyectos con `odoo_location_id` y `3378` filas en `odoo_sync_log`).
5. **Estado real de Odoo al terminar**: total de `stock.location` (se espera **8**, sin cambios) y cantidad de hijos de la ubicación 12 (se espera **1**).
6. **Desvíos:** todo punto donde la implementación se apartó del plan, o donde el valor real no coincidió con el esperado, con la explicación. Si no hubo ninguno, decirlo explícitamente.
7. **Dudas o bloqueos** pendientes.

Y `docs/fase1_recon_ubicaciones.md` con la salida del reconocimiento (Fase 1),
sin credenciales.

## Qué se va a verificar del otro lado

El reporte se corrobora contra el sistema real: se relee el diff completo, se
vuelven a correr los tests y el `--dry-run`, y se consulta Odoo y la BD local de
forma independiente. Los puntos que se van a mirar con lupa:

- Que `sanitize_location_name` sea **la misma función** usada al buscar y al crear (el bug que duplicaría una ubicación por corrida).
- Que `resolve_production_location` rechace candidatos cuyo padre sea `Production` (hoy ya hay 2 registros con `usage='production'`: ids 12 y 16 — el caso no es teórico).
- Que la búsqueda global previa a crear exista y realmente evite el `create`.
- Que `get_ejecucion_inicio` **no** filtre por `timestamp_fin`.
- Que ningún camino del código caiga a "sincronizar todos los proyectos" cuando no hay corrida válida.
- Que el `--dry-run` no haya escrito nada, en ningún lado.
- Que los tests nuevos no hagan red y pasen sin `.env`.
- Que no haya credenciales ni usuario del ERP en código, logs, docs ni reporte.

Los desvíos van a volver como un prompt de corrección, y se itera hasta que el
plan se cumpla completo.
