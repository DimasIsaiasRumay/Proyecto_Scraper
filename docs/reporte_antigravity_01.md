# Reporte de Ejecución — Iteración 1: Ubicaciones de Producción en Odoo

**Fecha:** 18 de agosto de 2026  
**Rama de trabajo:** `feat/ubicaciones-produccion`  
**Base:** `main`  
**Alcance ejecutado:** Fases 0 a 8 del plan `docs/plan_stock_locations.md`

---

## 1. Resumen de Ejecución por Fase (0 a 8)

### Fase 0 — Preparación
- **Qué se hizo:** Se creó la rama `feat/ubicaciones-produccion` desde `main`. Se ejecutó el baseline de pytest (`38 passed in 0.26s`). Se verificó la existencia de `scraper-fabricacion/data/fabricacion.db` y que las 4 claves en `odoo-integration/.env` tuvieran largo no nulo (`ODOO_URL`: 27, `ODOO_DATABASE`: 10, `ODOO_API_KEY`: 40, `DB_PATH`: 42).
- **Hash de commit:** N/A (fase de preparación y verificación de entorno).
- **Criterio de aceptación y resultado real:**
  - `git branch --show-current`: `feat/ubicaciones-produccion`
  - Baseline de tests: `38 passed in 0.26s`

---

### Fase 1 — Reconocimiento en Odoo real (solo lectura)
- **Qué se hizo:** Se creó el script de exploración `scripts/manual_exploration/explorar_ubicaciones_odoo.py` y se ejecutaron las 8 consultas en modo solo lectura (`search_read` y `fields_get`) contra el Odoo de producción. Se generó el documento `docs/fase1_recon_ubicaciones.md` con los resultados crudos sin credenciales.
- **Hash de commit:** `273c870` (`feat(scripts): script de exploración de stock.location en Odoo (Fase 1)`)
- **Criterio de aceptación y resultado real:**
  - `res.company` → 1 fila: `[{"id": 1, "name": "SET IN SAS"}]`
  - `ir.model.data` (`location_production` / `stock_location_production`) → `[]` (se adopta fallback por nombre/usage).
  - Padre por nombre (`name='Production'`, `location_id=False`) → `[{"id": 12, "name": "Production", "complete_name": "Production", "usage": "production", "location_id": False, "company_id": [1, "SET IN SAS"], "active": True}]`
  - Registros con `usage='production'` → 2 filas: ID 12 (`Production`) y ID 16 (`OP-CTOM-GAB-120826-0002`).
  - Hijos actuales de ID 12 → 1 fila: ID 16 (`OP-CTOM-GAB-120826-0002`).
  - Total `stock.location` → 8 activas (16 incluyendo inactivas).
  - Choque de nombres (25 proyectos corrida 39) → 1 coincidencia (`OP-CTOM-GAB-120826-0002`, ID 16).
  - `fields_get` → `usage` tipo `selection` (incluye `"production"`), `name` `required=True`, `complete_name` `readonly=True`.

---

### Fase 2 — Columna `odoo_location_id` + modelos
- **Qué se hizo:** Se actualizó `ensure_odoo_id_columns()` en `odoo-integration/database_reader.py` para agregar de forma idempotente la columna `odoo_location_id INTEGER` a la tabla `proyectos`. Se agregó la función `save_project_location_id(proyecto_nombre, location_id)`. Se actualizó `odoo-integration/odoo_models.py` agregando `odoo_location_id` a `ProyectoLocal` y eliminando `ProductoLocal` y el campo `productos`.
- **Hash de commit:** `6e9297c` (`feat(odoo): columna odoo_location_id y limpieza de modelos (Fase 2)`)
- **Criterio de aceptación y resultado real:**
  - Columnas en tabla `proyectos`: `['nombre', 'cliente', 'estado', 'fecha_primera_carga', 'fecha_ultima_sync', 'odoo_id', 'odoo_location_id']`
  - Idempotencia verificada en segunda corrida sin errores ni duplicaciones.

---

### Fase 3 — Selección de proyectos por corrida (`database_reader.py`)
- **Qué se hizo:** Se implementaron `get_ultima_ejecucion_valida()`, `get_ejecucion_inicio(ejecucion_id)` (sin filtro por `timestamp_fin`) y `get_projects_desde(timestamp_inicio)` (con orden alfabético por nombre y mapeo a `ProyectoLocal`). Se eliminaron las funciones en desuso (`get_productos`, `get_all_projects_with_productos`, `get_all_projects_typed`, `save_producto_odoo_id`, `get_producto_count`, `get_all_projects`).
- **Hash de commit:** `9fbc400` (`feat(odoo): seleccionar proyectos por corrida en database_reader (Fase 3)`)
- **Criterio de aceptación y resultado real:**
  - `d.get_ultima_ejecucion_valida()`: `{'id': 39, 'timestamp_inicio': '2026-08-18T11:29:06.546841'}`
  - `len(d.get_projects_desde(e['timestamp_inicio']))`: `25`
  - Corrida 36 descartada correctamente.

---

### Fase 4 — Creador de ubicaciones (`sync_locations.py`)
- **Qué se hizo:** Se creó `odoo-integration/sync_locations.py` con `sanitize_location_name()` (reemplazo `/` por `-`), `resolve_production_location()` (con búsqueda por XML ID, fallback defensivo que rechaza sub-ubicaciones hijas y normalización de `company_id`), `build_location_vals()` y `sync_one_location()` (búsqueda bajo el padre, búsqueda global anti-colisiones y creación). Se eliminaron `odoo-integration/sync_projects.py` y `odoo-integration/sync_tasks.py` vía `git rm`.
- **Hash de commit:** `ac6efe2` (`feat(odoo): sync_locations.py crea ubicaciones de producción (Fase 4)`)
- **Criterio de aceptación y resultado real:** Archivo creado, eliminación registrada en git.

---

### Fase 5 — Orquestador (`odoo_sync.py`) + integración con el bot
- **Qué se hizo:** Se reescribió `odoo-integration/odoo_sync.py` para sincronizar `stock.location` por corrida (`--dry-run`, `--only-projects`, `--ejecucion-id`, `--limit`). Se simplificaron contadores a `created`, `sin_cambios`, `aviso`, `error` con códigos de salida `0` (ok), `1` (fatal) y `2` (errores por proyecto). Se actualizó `scraper-fabricacion/main.py:416` pasando `ejecucion_id=ejecucion_id` con su comentario aclaratorio.
- **Hash de commit:** `8034706` (`refactor(odoo): orquestador de ubicaciones y baja de sync_projects/sync_tasks (Fase 5)`)
- **Criterio de aceptación y resultado real:**
  - `python odoo_sync.py --help` exhibe los 4 flags.
  - `python -c "import sys; sys.path.insert(0,'odoo-integration'); import odoo_sync"` importa limpiamente sin `.env`.

---

### Fase 6 — Verificación en simulación (`--dry-run`)
- **Qué se hizo:** Se ejecutó `python odoo_sync.py --dry-run` contra Odoo real. Se comprobó la resolución de la corrida #39, el padre `Production` (ID 12), las 25 consultas y el resultado de 24 ubicaciones que se crearían y 1 sin cambios (`OP-CTOM-GAB-120826-0002`, ID 16).
- **Hash de commit:** `632b357` (`feat(odoo): dry-run con lecturas reales contra Odoo (Fase 6)`)
- **Criterio de aceptación y resultado real:**
  - Corrida usada: #39 (inicio `2026-08-18T11:29:06.546841`)
  - Proyectos de la corrida: 25 (BD local: 82)
  - Padre: Production, ID 12, empresa: 1
  - Creadas (se crearían): 24
  - Sin cambios: 1 (`OP-CTOM-GAB-120826-0002`, Odoo ID 16)
  - Avisos: 0
  - Errores: 0
  - Código de salida: 0
  - Conteo BD antes y después: `con location_id: 0`, `log filas: 3378` (invariante).

---

### Fase 7 — Pruebas automáticas
- **Qué se hizo:** Se eliminó `tests/test_odoo_builders.py`. Se crearon `tests/test_odoo_locations.py` (18 tests unitarios con `FakeClient`) y `tests/test_run_selection.py` (10 tests con base de datos SQLite temporal aislada).
- **Hash de commit:** `5cd5361` (`test(odoo): pruebas de ubicaciones y de selección por corrida (Fase 7)`)
- **Criterio de aceptación y resultado real:**
  - `python -m pytest -q` → 60 tests pasados (28 tests nuevos, superior al mínimo de 28).
  - Ninguna dependencia de red en tests (`grep -rn "requests\|OdooClient()" tests/` vacío).
  - Verificado en Python 3.10 vía compilación de bytecode y ejecución en pytest.

---

### Fase 8 — Documentación (README + plan)
- **Qué se hizo:** Se actualizó `README.md` (diagramas de arquitectura §2 y §6, árbol §3, esquema ER §4 con `odoo_location_id`, nueva sección §6 de `stock.location`, entrada de cambios recientes §7 y guía de operación §8 con los 4 flags). Se actualizó `docs/plan_stock_locations.md` marcando Fases 0 a 8 en `✅ Hecho`. Se generó el presente reporte `docs/reporte_antigravity_01.md`.
- **Hash de commit:** `6860162` (`docs: README y plan al día con las ubicaciones de producción (Fase 8)`)
- **Criterio de aceptación y resultado real:** Documentación sincronizada con el estado actual del sistema.

---

## 2. Salidas Completas y Sin Editar

### `python -m pytest -q`
```
............................................................             [100%]
60 passed in 0.44s
```

### `git log --oneline main..feat/ubicaciones-produccion`
```
6860162 docs: README y plan al día con las ubicaciones de producción (Fase 8)
5cd5361 test(odoo): pruebas de ubicaciones y de selección por corrida (Fase 7)
632b357 feat(odoo): dry-run con lecturas reales contra Odoo (Fase 6)
8034706 refactor(odoo): orquestador de ubicaciones y baja de sync_projects/sync_tasks (Fase 5)
ac6efe2 feat(odoo): sync_locations.py crea ubicaciones de producción (Fase 4)
9fbc400 feat(odoo): seleccionar proyectos por corrida en database_reader (Fase 3)
6e9297c feat(odoo): columna odoo_location_id y limpieza de modelos (Fase 2)
273c870 feat(scripts): script de exploración de stock.location en Odoo (Fase 1)
```

### `git diff --stat main..feat/ubicaciones-produccion`
```
 README.md                                          | 305 ++++-----
 docs/fase1_recon_ubicaciones.md                    | 341 ++++++++++
 docs/plan_stock_locations.md                       | 736 +++++++++++++++++++++
 docs/reporte_antigravity_01.md                     | 322 +++++++++
 odoo-integration/database_reader.py                | 128 ++--
 odoo-integration/odoo_models.py                    |  57 +-
 odoo-integration/odoo_sync.py                      | 258 ++++----
 odoo-integration/sync_locations.py                 | 274 ++++++++
 odoo-integration/sync_projects.py                  | 164 -----
 odoo-integration/sync_tasks.py                     | 183 -----
 scraper-fabricacion/main.py                        |   3 +-
 .../explorar_ubicaciones_odoo.py                   | 147 ++++
 tests/test_odoo_builders.py                        |  91 ---
 tests/test_odoo_locations.py                       | 443 +++++++++++++
 tests/test_run_selection.py                        | 152 +++++
 15 files changed, 2761 insertions(+), 843 deletions(-)
```

### `cd odoo-integration && python odoo_sync.py --dry-run`
```
2026-08-18 14:22:45 | INFO     | ======================================================================
2026-08-18 14:22:45 | INFO     | INICIO DE SINCRONIZACIÓN CON ODOO — 2026-08-18 14:22:45
2026-08-18 14:22:45 | INFO     | ⚠️  MODO DRY-RUN: No se realizarán cambios en Odoo ni en la BD local
2026-08-18 14:22:45 | INFO     | ======================================================================
2026-08-18 14:22:45 | INFO     | 📡 Conectando a Odoo (https://set-in-sas.odoo.com)...
2026-08-18 14:22:45 | INFO     | 📡 [DRY-RUN] Se omite la verificación de conexión con Odoo (config ya validada).
2026-08-18 14:22:45 | INFO     | 📌 Corrida usada: #39 (inicio 2026-08-18T11:29:06.546841)
2026-08-18 14:22:49 | INFO     | 🏭 Ubicación padre: 'Production' (Odoo ID: 12, empresa: 1)
2026-08-18 14:22:49 | INFO     | 📂 Proyectos de la corrida: 25 (BD local: 82)
2026-08-18 14:22:49 | INFO     | 
🔄 Procesando 25 proyectos...
2026-08-18 14:22:49 | INFO     | 
[1/25] Proyecto: 'OP-AMX-EMIX-070826-0001'
2026-08-18 14:22:51 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP-AMX-EMIX-070826-0001' bajo Production (ID 12)
2026-08-18 14:22:51 | INFO     | 
[2/25] Proyecto: 'OP-AMX-SUM-070826-0002'
2026-08-18 14:22:54 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP-AMX-SUM-070826-0002' bajo Production (ID 12)
2026-08-18 14:22:54 | INFO     | 
[3/25] Proyecto: 'OP-CTOM-GAB-120826-0002'
2026-08-18 14:22:55 | INFO     |   ➖ Ubicación ya existía: 'OP-CTOM-GAB-120826-0002' (Odoo ID: 16)
2026-08-18 14:22:55 | INFO     | 
[4/25] Proyecto: 'OP-CTOM-SMX-120826-0003'
2026-08-18 14:22:57 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP-CTOM-SMX-120826-0003' bajo Production (ID 12)
2026-08-18 14:22:57 | INFO     | 
[5/25] Proyecto: 'OP-ING-EPLIQ-070826-0001'
2026-08-18 14:22:58 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP-ING-EPLIQ-070826-0001' bajo Production (ID 12)
2026-08-18 14:22:58 | INFO     | 
[6/25] Proyecto: 'OP-MET-SMX-120826-0002'
2026-08-18 14:23:00 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP-MET-SMX-120826-0002' bajo Production (ID 12)
2026-08-18 14:23:00 | INFO     | 
[7/25] Proyecto: 'OP-SSTK-FTTH-110826-0001'
2026-08-18 14:23:02 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP-SSTK-FTTH-110826-0001' bajo Production (ID 12)
2026-08-18 14:23:02 | INFO     | 
[8/25] Proyecto: 'OP-TECO-FTTH-120826-0001'
2026-08-18 14:23:04 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP-TECO-FTTH-120826-0001' bajo Production (ID 12)
2026-08-18 14:23:04 | INFO     | 
[9/25] Proyecto: 'OP-TECO-PET-120826-0002'
2026-08-18 14:23:06 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP-TECO-PET-120826-0002' bajo Production (ID 12)
2026-08-18 14:23:06 | INFO     | 
[10/25] Proyecto: 'OP_CLARO_BANDEJA SOLAR_0403260846'
2026-08-18 14:23:08 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_CLARO_BANDEJA SOLAR_0403260846' bajo Production (ID 12)
2026-08-18 14:23:08 | INFO     | 
[11/25] Proyecto: 'OP_CLARO_COW12 3_ADD_PUNTA Y SUMINISTROS EXTRA_2905260918'
2026-08-18 14:23:09 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_CLARO_COW12 3_ADD_PUNTA Y SUMINISTROS EXTRA_2905260918' bajo Production (ID 12)
2026-08-18 14:23:09 | INFO     | 
[12/25] Proyecto: 'OP_CLARO_COW12 3_ESTRUCTURAL_01122217'
2026-08-18 14:23:11 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_CLARO_COW12 3_ESTRUCTURAL_01122217' bajo Production (ID 12)
2026-08-18 14:23:11 | INFO     | 
[13/25] Proyecto: 'OP_CLARO_COW_MATADICIONALES_0202261002'
2026-08-18 14:23:12 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_CLARO_COW_MATADICIONALES_0202261002' bajo Production (ID 12)
2026-08-18 14:23:12 | INFO     | 
[14/25] Proyecto: 'OP_CLARO_Complemento COWRoja_2906261616'
2026-08-18 14:23:14 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_CLARO_Complemento COWRoja_2906261616' bajo Production (ID 12)
2026-08-18 14:23:14 | INFO     | 
[15/25] Proyecto: 'OP_CLARO_MUERTOS DE HORIMGON_2412251533'
2026-08-18 14:23:16 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_CLARO_MUERTOS DE HORIMGON_2412251533' bajo Production (ID 12)
2026-08-18 14:23:16 | INFO     | 
[16/25] Proyecto: 'OP_CLARO_Muertos HA-COW12_1504261550'
2026-08-18 14:23:18 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_CLARO_Muertos HA-COW12_1504261550' bajo Production (ID 12)
2026-08-18 14:23:18 | INFO     | 
[17/25] Proyecto: 'OP_CLIENTE_ASADOR_0906261156'
2026-08-18 14:23:20 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_CLIENTE_ASADOR_0906261156' bajo Production (ID 12)
2026-08-18 14:23:20 | INFO     | 
[18/25] Proyecto: 'OP_Claro_Adecuacionpuertas PjeCarlosPAZ_1906261134'
2026-08-18 14:23:21 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_Claro_Adecuacionpuertas PjeCarlosPAZ_1906261134' bajo Production (ID 12)
2026-08-18 14:23:21 | INFO     | 
[19/25] Proyecto: 'OP_MULTIRADIO_Estructuras Paneles Solares_200726'
2026-08-18 14:23:23 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_MULTIRADIO_Estructuras Paneles Solares_200726' bajo Production (ID 12)
2026-08-18 14:23:23 | INFO     | 
[20/25] Proyecto: 'OP_TELECOM_BANQUINAS_1414260913'
2026-08-18 14:23:24 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_TELECOM_BANQUINAS_1414260913' bajo Production (ID 12)
2026-08-18 14:23:24 | INFO     | 
[21/25] Proyecto: 'OP_TELECOM_TBC200AG2026_2007261048'
2026-08-18 14:23:27 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_TELECOM_TBC200AG2026_2007261048' bajo Production (ID 12)
2026-08-18 14:23:27 | INFO     | 
[22/25] Proyecto: 'OP_TOTEM_PEdido Agosto_2807261155'
2026-08-18 14:23:28 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_TOTEM_PEdido Agosto_2807261155' bajo Production (ID 12)
2026-08-18 14:23:28 | INFO     | 
[23/25] Proyecto: 'OP_VIALTRUCK_Conjuntos varios_0107261205'
2026-08-18 14:23:30 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_VIALTRUCK_Conjuntos varios_0107261205' bajo Production (ID 12)
2026-08-18 14:23:30 | INFO     | 
[24/25] Proyecto: 'OP_VIALTRUCK_G BASTIDORES_2707260847'
2026-08-18 14:23:32 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_VIALTRUCK_G BASTIDORES_2707260847' bajo Production (ID 12)
2026-08-18 14:23:32 | INFO     | 
[25/25] Proyecto: 'OP_VIALTRUCK_Nicolas B_2307261303'
2026-08-18 14:23:33 | INFO     |   🆕 [DRY-RUN] Crearía ubicación: 'OP_VIALTRUCK_Nicolas B_2307261303' bajo Production (ID 12)
2026-08-18 14:23:33 | INFO     | 
======================================================================
2026-08-18 14:23:33 | INFO     | RESUMEN DE SIMULACIÓN (DRY-RUN)
2026-08-18 14:23:33 | INFO     | ======================================================================
2026-08-18 14:23:33 | INFO     |   Duración: 48.6 segundos
2026-08-18 14:23:33 | INFO     |   Ubicaciones — Creadas (se crearían): 24, Sin cambios: 1, Avisos: 0, Errores: 0
2026-08-18 14:23:33 | INFO     | ======================================================================
2026-08-18 14:23:33 | INFO     | ✅ Sincronización completada sin errores.
```

### `cd odoo-integration && python odoo_sync.py --help`
```
usage: odoo_sync.py [-h] [--dry-run] [--only-projects]
                    [--ejecucion-id EJECUCION_ID] [--limit LIMIT]

Sincronización de ubicaciones de producción con Odoo vía API JSON-2

options:
  -h, --help            show this help message and exit
  --dry-run             Simula la sincronización sin hacer cambios en Odoo ni
                        en la BD local.
  --only-projects       Obsoleto: ya no se crean tareas/productos (no-op).
  --ejecucion-id EJECUCION_ID
                        ID de corrida puntual a sincronizar (por defecto:
                        última corrida válida).
  --limit LIMIT         Limita la cantidad de proyectos a procesar.

Ejemplos:
  python odoo_sync.py                      # última corrida válida
  python odoo_sync.py --dry-run            # simulación real (solo lecturas)
  python odoo_sync.py --limit 1            # smoke test contra un solo proyecto
  python odoo_sync.py --ejecucion-id 39    # corrida puntual
```

---

## 3. Pruebas de Limpieza

### `grep -rn "sync_projects\|sync_tasks" --include=*.py .`
```
(Salida vacía - 0 coincidencias)
```

### `grep -rn "get_all_projects\|get_productos\|get_producto_count\|save_producto_odoo_id\|get_all_projects_typed\|ProductoLocal" --include=*.py .`
```
(Salida vacía - 0 coincidencias)
```

---

## 4. Prueba de Invarianza del Dry-Run

Comando ejecutado:
```bash
python -c "import sys; sys.path.insert(0,'odoo-integration'); import sqlite3, database_reader as d; c=sqlite3.connect(d.get_db_path()); print('con location_id:', c.execute('SELECT COUNT(*) FROM proyectos WHERE odoo_location_id IS NOT NULL').fetchone()[0]); print('log filas:', c.execute('SELECT COUNT(*) FROM odoo_sync_log').fetchone()[0])"
```

- **Antes de `--dry-run`:**
  ```
  con location_id: 0
  log filas: 3378
  ```
- **Después de `--dry-run`:**
  ```
  con location_id: 0
  log filas: 3378
  ```
Ambos conteos son estrictamente idénticos: el dry-run no escribió ningún registro en la base de datos local ni en `odoo_sync_log`.

---

## 5. Estado Real de Odoo al Terminar

Consulta ejecutada:
```bash
python -c "import sys; sys.path.insert(0,'odoo-integration'); from odoo_client import OdooClient; c=OdooClient(); print('activas stock.location:', len(c.search_read('stock.location', [['active','=',True]], ['id'], limit=200))); print('hijos de location 12:', len(c.search_read('stock.location', [['location_id','=',12]], ['id','name'], limit=100)))"
```
- **Total `stock.location` activas en Odoo:** `8` (sin cambios respecto al inicio).
- **Total hijos de la ubicación 12 (`Production`):** `1` (`OP-CTOM-GAB-120826-0002`, ID 16, sin cambios).

---

## 6. Desvíos

**Ninguno.**  
La implementación siguió de forma exacta cada una de las directivas, firmas, algoritmos de resolución y criterios de aceptación estipulados en `docs/plan_stock_locations.md`.

---

## 7. Dudas o Bloqueos Pendientes

- **Fase 9:** No se han realizado operaciones de escritura (`create`, `write`, `unlink`) contra el Odoo de producción. El sistema queda listo y a la espera de la autorización explícita para la ejecución de la Fase 9 (`--limit 1` piloto, y posterior sincronización completa).
