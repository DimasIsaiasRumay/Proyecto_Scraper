# Plan: Ubicaciones de Producción por Proyecto en Odoo

> Reemplaza la sincronización de Proyectos/Tareas (`project.project` / `project.task`)
> por la creación de Ubicaciones Virtuales de Producción (`stock.location`), una por
> cada proyecto que el bot procesó en su última corrida.
>
> **Plan de ejecución exacto.** Este documento es el contrato: define archivo por
> archivo, firma por firma y criterio de aceptación por fase. Se actualiza en vivo
> (no es histórico congelado como [`historial/`](historial/)).
>
> Numeración en **orden de ejecución** (antes el orden lógico y la numeración no
> coincidían). Mapeo con la versión anterior del plan:
> `F1=1 · F2=5 · F3=2 · F4=3 · F5=4 · F6=6 · F7=7 · F8=8 · F9=nueva`.

## Estado general

| Fase | Descripción | Estado |
|---|---|---|
| 0 | Preparación (rama, entorno, baseline verde) | ✅ Hecho |
| 1 | Reconocimiento en Odoo real (solo lectura) | ✅ Hecho |
| 2 | Columna `odoo_location_id` + modelos | ✅ Hecho |
| 3 | Selección de proyectos por corrida (`database_reader.py`) | ✅ Hecho |
| 4 | Creador de ubicaciones (`sync_locations.py`) | ✅ Hecho |
| 5 | Orquestador (`odoo_sync.py`) + integración con el bot | ✅ Hecho |
| 6 | Verificación en simulación (`--dry-run`) | ✅ Hecho |
| 7 | Pruebas automáticas | ✅ Hecho |
| 8 | Documentación (README + este plan) | ✅ Hecho |
| 9 | Corrida real: `--limit 1`, luego lote completo | ⬜ Pendiente (requiere aprobación) |

Marcadores: ⬜ Pendiente · 🔄 En curso · ✅ Hecho · ⏸️ Bloqueado

---

## Datos verificados contra el sistema real (18/08/2026)

Estos valores salieron de consultas reales, no de supuestos. Son los números
contra los que se validan las fases.

### Odoo (`stock.location`, solo lectura)

| Dato | Valor |
|---|---|
| Empresas (`res.company`) | 1 — `SET IN SAS` (id 1) |
| `Production` | id **12**, `name='Production'`, `complete_name='Production'`, `usage='production'`, `location_id=false`, `company_id=[1,'SET IN SAS']`, `active=true` |
| Hijos actuales de `Production` | **1** — id **16**, `OP-CTOM-GAB-120826-0002`, `complete_name='Production/OP-CTOM-GAB-120826-0002'`, `usage='production'` |
| Registros con `usage='production'` | **2** (id 12 y id 16) — la trampa de resolver el padre por `usage` ya es real |
| Total `stock.location` | 8 |
| `ir.model.data` (`module='stock'`, `name='stock_location_production'`) | 0 filas → el XML id **no** responde a ese nombre; probar `name='location_production'` (Fase 1) |

### BD local (`scraper-fabricacion/data/fabricacion.db`)

| Dato | Valor |
|---|---|
| Total proyectos | 82 |
| Columnas de `proyectos` | `nombre, cliente, estado, fecha_primera_carga, fecha_ultima_sync, odoo_id` (**no** existe `odoo_location_id`) |
| Última corrida válida | id **39**, `timestamp_inicio='2026-08-18T11:29:06.546841'`, `timestamp_fin='2026-08-18T11:50:41.050068'`, `estado='completado_con_errores'`, `proyectos_procesados=23` |
| Proyectos con `fecha_ultima_sync >= ` inicio de #39 | **25** |
| Por qué 25 y no 23 | `upsert_proyecto()` escribe la fila antes de scrapear el detalle; 2 proyectos fallaron después (`OP-ING-EPLIQ-070826-0001`, `OP_CLARO_Complemento COWRoja_2906261616`) y no cuentan en `proyectos_procesados`, pero sí quedaron actualizados. **25 es el valor correcto**, no un bug. |
| Corridas que el filtro debe descartar | id 36 (`timestamp_fin IS NULL`, `proyectos_procesados=0`) |
| Nombres con `/` | 1 — `OP_ITC_Caja p/Baterias_1504261521` |
| Otros caracteres presentes en nombres | `"` (`OP_TOTEM_INC32"_2605260826`), `()` (`OP_TELECOM_MORSETOS26 (2)_1603260739`), `.` (`OP_VIALTRUCK_VOLCADORA9.3_2005260959`), espacios internos |
| Largo máximo de nombre | 61 caracteres |
| `odoo_sync_log` | existe, 3378 filas (sistema viejo) |

**Consecuencia directa:** de los 25 proyectos de la corrida 39, hoy **1 ya existe**
en Odoo (`OP-CTOM-GAB-120826-0002`) y **24 se crearían**. Ese es el resultado
esperado del `--dry-run` de la Fase 6.

---

## Decisiones cerradas (no se re-discuten durante la implementación)

| # | Decisión |
|---|---|
| 1 | La sincronización corre después del bot, en el mismo proceso (`main.py --sync`), recibiendo `ejecucion_id`. Corrida suelta → última corrida con `timestamp_fin IS NOT NULL AND proyectos_procesados > 0`. |
| 2 | Se crea ubicación para **todos** los proyectos de la corrida, sin filtrar por `estado` (`Material OK` / `Sin Material`). |
| 3 | Si la ubicación existe pero fue modificada a mano en Odoo (padre, `usage` o `active` distintos), el script **no la toca**: registra `aviso`. |
| 4 | `sync_projects.py` y `sync_tasks.py` se **borran** (quedan en git). Sus tests también. |
| 5 | `/` en el nombre se reemplaza por `-` (Odoo usa `/` como separador de jerarquía). |
| 6 | Se agrega la columna `odoo_location_id` a `proyectos` (auditoría). |
| 7 | Los 81 `project.project` + 131 `project.task` ya cargados **quedan como están**: no se tocan, no se borran. |
| 8 | Nada de este trabajo toca `.env`, ni imprime `ODOO_URL` / `ODOO_DATABASE` / `ODOO_API_KEY` / usuario del ERP en logs, docs o salida de consola. |
| 9 | Las ubicaciones creadas llevan `usage='production'` explícito (el default de Odoo para un hijo es `internal`; el hijo id 16 ya creado usa `production`). |
| 10 | Códigos de salida de `run_sync()`: **0** = sin errores · **1** = error fatal (BD, credenciales, sin corrida válida, `Production` no resuelto) · **2** = terminó con errores por proyecto. Los `aviso` **no** cambian el código de salida. |

---

## Fase 0 — Preparación

**Estado:** ✅ Hecho

1. Rama nueva desde `main`: `feat/ubicaciones-produccion`. Nunca commitear a `main`. Nunca `git push`.
2. Baseline verde antes de tocar nada:
   ```bash
   python -m pytest -q
   ```
   Guardar la salida en el reporte. Si ya está roja, se informa y se detiene.
3. Confirmar que existe `scraper-fabricacion/data/fabricacion.db` y que `odoo-integration/.env` tiene las 4 claves cargadas (verificar **largo no nulo**, sin imprimir valores).
4. Un commit por fase, mensaje `<tipo>(<ámbito>): <qué> (Fase N)`, en español, sin `Co-Authored-By`.

**Criterio de aceptación:** `git branch --show-current` = `feat/ubicaciones-produccion`; pytest baseline registrado.

---

## Fase 1 — Reconocimiento en Odoo real (solo lectura)

**Estado:** ✅ Hecho

**Archivo nuevo:** `scripts/manual_exploration/explorar_ubicaciones_odoo.py`

Mismo formato que los otros scripts de esa carpeta (ver `test_login.py`): docstring
que aclara que es exploración manual, que golpea Odoo de producción, que **no** lo
corre pytest, y que **no imprime credenciales**.

Solo `search_read`. **Prohibido** `create` y `write` en esta fase.

### Consultas exactas que debe hacer

```python
# 1. Empresas
client.search_read("res.company", [], ["id", "name"], limit=10)

# 2. XML id del padre — probar los dos nombres candidatos, en este orden
client.search_read("ir.model.data",
    [["module", "=", "stock"], ["name", "=", "location_production"]],
    ["id", "module", "name", "model", "res_id"], limit=5)
client.search_read("ir.model.data",
    [["module", "=", "stock"], ["name", "=", "stock_location_production"]],
    ["id", "module", "name", "model", "res_id"], limit=5)

# 3. Padre por nombre (fallback)
client.search_read("stock.location",
    [["name", "=", "Production"], ["location_id", "=", False]],
    ["id", "name", "complete_name", "usage", "location_id", "company_id", "active"], limit=10)

# 4. Todo lo que tenga usage=production (para ver la trampa)
client.search_read("stock.location", [["usage", "=", "production"]],
    ["id", "name", "complete_name", "usage", "location_id", "active"], limit=50)

# 5. Hijos actuales del padre resuelto
client.search_read("stock.location", [["location_id", "=", <padre_id>]],
    ["id", "name", "complete_name", "usage", "active"], limit=100)

# 6. Inventario completo, incluyendo archivadas
client.search_read("stock.location", [["active", "in", [True, False]]],
    ["id", "name", "complete_name", "usage", "location_id", "active"], limit=200)

# 7. Choque de nombres: los 25 nombres de la corrida 39 ya saneados
client.search_read("stock.location",
    [["name", "in", [<lista de 25 nombres saneados>]], ["active", "in", [True, False]]],
    ["id", "name", "complete_name", "location_id", "usage", "active"], limit=50)

# 8. Metadatos de campos (confirma tipo/required/readonly de lo que vamos a escribir)
client._call("stock.location", "fields_get",
    {"allfields": ["name", "usage", "location_id", "company_id", "active", "complete_name"],
     "attributes": ["type", "required", "readonly", "store", "selection"]})
```

Para el punto 7 el script lee los nombres de la BD local con las funciones de la
Fase 3 si ya existen; si no, con SQL directo (query de la Fase 3, sección c).

### Salida

Reporte en `docs/fase1_recon_ubicaciones.md`: cada consulta con su resultado
crudo (JSON recortado), **sin** URL, base de datos, API key ni usuario del ERP.

### Criterios de aceptación (valores esperados hoy)

- `res.company` → 1 fila, id 1.
- Consulta 3 → **id 12**, `usage='production'`, `location_id=false`, `company_id=[1, ...]`.
- Consulta 4 → **2 filas** (id 12 y id 16). Si devuelve 1, alguien borró el hijo; si devuelve más, se crearon más a mano: se informa antes de seguir.
- Consulta 5 → 1 fila: id 16 `OP-CTOM-GAB-120826-0002`.
- Consulta 6 → 8 activas (más las archivadas que aparezcan).
- Consulta 7 → **1 coincidencia** (`OP-CTOM-GAB-120826-0002`).
- Consulta 2 → si alguno de los dos nombres devuelve fila, **ese es el método principal** de la Fase 4b; si los dos devuelven vacío o el modelo no es accesible, queda el fallback por nombre y se anota en el reporte.
- `fields_get` → `usage` es `selection` con `'production'` entre las opciones; `name` `required=True`; `complete_name` `readonly`/computado (**no** se escribe nunca).

**Riesgo:** ninguno (solo lectura). **Commit:** `feat(scripts): script de exploración de stock.location en Odoo (Fase 1)`.

---

## Fase 2 — Columna `odoo_location_id` + modelos

**Estado:** ✅ Hecho

Va antes de las Fases 3 y 4 porque ambas leen y escriben esta columna.

### 2a. `odoo-integration/database_reader.py` → `ensure_odoo_id_columns()`

Agregar, siguiendo el patrón exacto que ya usa la función (línea 62-71):

```python
if "odoo_location_id" not in columns_proyectos:
    conn.execute("ALTER TABLE proyectos ADD COLUMN odoo_location_id INTEGER")
```

No se elimina la columna `odoo_id` de `proyectos` ni la de `proyecto_productos`:
son datos históricos del sistema viejo (decisión 7). La función sigue siendo
idempotente y segura de correr en cada arranque.

### 2b. Función nueva de escritura

```python
def save_project_location_id(proyecto_nombre: str, location_id: int) -> None:
    """Guarda el ID de la ubicación de Odoo para un proyecto en la BD local."""
    # Misma estructura que save_project_odoo_id (líneas 153-163):
    # _connect() → with conn → UPDATE proyectos SET odoo_location_id = ? WHERE nombre = ?
```

### 2c. `odoo-integration/odoo_models.py`

- `ProyectoLocal` gana `odoo_location_id: Optional[int] = None`, leído en `from_row()` con `row.get("odoo_location_id")`.
- Se **eliminan**: la clase `ProductoLocal` completa y el campo `productos` de `ProyectoLocal` (quedan sin uso al borrarse `sync_tasks.py` en la Fase 5).
- Se ajusta el docstring del módulo: ya no menciona `sync_projects.py` / `sync_tasks.py`, sí `sync_locations.py`.
- `from_row()` mantiene el `raise ValueError` si falta `nombre`.

### Criterios de aceptación

```bash
python -c "import sys; sys.path.insert(0,'odoo-integration'); import database_reader as d; d.ensure_odoo_id_columns(); import sqlite3; c=sqlite3.connect(d.get_db_path()); print([r[1] for r in c.execute('PRAGMA table_info(proyectos)')])"
```
imprime la lista con `odoo_location_id` al final. Correrlo dos veces seguidas no
falla ni duplica la columna. `grep -rn "ProductoLocal" odoo-integration/` no
devuelve nada (después de la Fase 5, cuando ya no exista `sync_tasks.py`).

**Commit:** `feat(odoo): columna odoo_location_id y limpieza de modelos (Fase 2)`.

---

## Fase 3 — Selección de proyectos por corrida

**Estado:** ✅ Hecho

**Archivo:** `odoo-integration/database_reader.py`

### 3a. `get_ultima_ejecucion_valida()`

```python
def get_ultima_ejecucion_valida() -> Optional[Dict]:
    """Última corrida terminada y con proyectos procesados.
    Retorna {"id": int, "timestamp_inicio": str} o None si no hay ninguna."""
```
SQL exacto:
```sql
SELECT id, timestamp_inicio FROM ejecuciones
WHERE timestamp_fin IS NOT NULL AND proyectos_procesados > 0
ORDER BY id DESC LIMIT 1
```
El filtro **no** usa `estado`: ninguna corrida real quedó en `completado`; las
buenas son `completado_con_errores`.

### 3b. `get_ejecucion_inicio(ejecucion_id)`

```python
def get_ejecucion_inicio(ejecucion_id: int) -> Optional[str]:
    """timestamp_inicio de una corrida puntual. None si el id no existe."""
```
```sql
SELECT timestamp_inicio FROM ejecuciones WHERE id = ?
```
**Sin** filtro de `timestamp_fin`: cuando el bot llama a la sincronización
(`main.py`, dentro del `try`), la corrida en curso todavía tiene
`timestamp_fin = NULL` — `finalizar_ejecucion()` corre después, en el `finally`.
Si esta función filtrara por fin, el modo integrado nunca encontraría su propia corrida.

### 3c. `get_projects_desde(timestamp_inicio)`

```python
def get_projects_desde(timestamp_inicio: str) -> List[ProyectoLocal]:
```
```sql
SELECT nombre, cliente, estado, odoo_id, odoo_location_id
FROM proyectos
WHERE fecha_ultima_sync >= ?
ORDER BY nombre
```
Construye `ProyectoLocal.from_row(dict(row))`, saltando (con `continue`) los que
levanten `ValueError`. No trae productos: una sola consulta en vez de 1+82.

**Por qué comparar fechas como texto funciona:** ambas columnas guardan ISO
(`datetime.now().isoformat()`, ej. `2026-08-18T11:29:06.546841`), que ordena
correctamente como string y tiene largo fijo. `iniciar_ejecucion()` registra el
inicio antes de scrapear, así que todo proyecto tocado en la corrida queda con
`fecha_ultima_sync >=` ese valor.

### 3d. Funciones que se eliminan

`get_productos`, `get_all_projects_with_productos`, `get_all_projects_typed`,
`save_producto_odoo_id`, `get_producto_count`, `get_all_projects`.

Se conservan: `_get_db_path`, `_connect`, `ensure_odoo_id_columns`,
`save_project_odoo_id` (histórico), `save_project_location_id`,
`get_project_count`, y los alias públicos `get_db_path` / `connect_db` (los usa
`sync_logger.py`).

**Prueba obligatoria de que no quedó nada colgado:**
```bash
grep -rn "get_all_projects\|get_productos\|get_producto_count\|save_producto_odoo_id\|get_all_projects_typed" --include=*.py .
```
debe devolver **cero** líneas al terminar la Fase 7.

### Criterios de aceptación (datos reales)

```bash
python -c "import sys; sys.path.insert(0,'odoo-integration'); import database_reader as d; e=d.get_ultima_ejecucion_valida(); print(e); print(len(d.get_projects_desde(e['timestamp_inicio'])))"
```
imprime `{'id': 39, 'timestamp_inicio': '2026-08-18T11:29:06.546841'}` y luego `25`.
La corrida 36 (`timestamp_fin=NULL`, 0 proyectos) no puede ser elegida.

**Commit:** `feat(odoo): seleccionar proyectos por corrida en database_reader (Fase 3)`.

---

## Fase 4 — Creador de ubicaciones

**Estado:** ✅ Hecho

**Archivo nuevo:** `odoo-integration/sync_locations.py` (reemplaza `sync_projects.py`)

### Constantes

```python
_MODEL = "stock.location"
_SEARCH_FIELDS = ["id", "name", "complete_name", "usage", "location_id", "active"]
_XMLID_CANDIDATES = (("stock", "location_production"), ("stock", "stock_location_production"))
_USAGE = "production"
```

### 4a. `sanitize_location_name`

```python
def sanitize_location_name(nombre: str) -> str:
    """Nombre apto para stock.location: '/' es separador de jerarquía en Odoo."""
```
Reglas, en este orden y sin agregar ninguna otra:
1. `nombre.strip()`
2. reemplazar `/` por `-`

No se tocan `"`, `(`, `)`, `.`, ni los espacios internos: Odoo los acepta y
cambiarlos rompería la correspondencia con el nombre del ERP.

⚠️ **Punto crítico:** esta única función se usa **al buscar y al crear**. Si se
sanea solo al crear, la búsqueda nunca encuentra el registro existente y se
duplica la ubicación en cada corrida. Tiene test de regresión propio (Fase 7).

### 4b. `resolve_production_location`

```python
@dataclass
class ProductionParent:
    id: int
    company_id: Optional[int] = None

def resolve_production_location(client: OdooClient) -> Optional[ProductionParent]:
    """Resuelve la ubicación padre 'Production'. Se llama UNA vez por corrida.
    None → la sincronización completa se aborta (sin padre no hay nada que crear)."""
```

Algoritmo exacto:

1. **Por XML id** — para cada par de `_XMLID_CANDIDATES`:
   `search_read("ir.model.data", [["module","=",mod],["name","=",name]], ["res_id"], limit=1)`.
   Si hay `res_id`, leer ese `stock.location` con `_SEARCH_FIELDS` + `company_id`
   y pasarlo por la validación del punto 3.
2. **Fallback por nombre** (solo si 1 no dio resultado válido):
   `search_read(_MODEL, [["usage","=","production"],["location_id","=",False],["active","=",True]], _SEARCH_FIELDS + ["company_id"], limit=5)`.
   - exactamente 1 → candidato.
   - 0 → segundo intento: `[["name","=","Production"],["location_id","=",False],["active","=",True]]`.
   - más de 1 → **abortar**: loguear los candidatos (id + `complete_name`) y devolver `None`. Nunca elegir "el primero".
3. **Validación del candidato** (la que evita el bug de la 2ª corrida):
   - `usage == "production"`, y
   - `active` es verdadero, y
   - **no** es una de nuestras propias sub-ubicaciones: se rechaza si tiene padre
     y el nombre de ese padre es `Production` (`location_id[1] == "Production"`).
4. `company_id` se normaliza: Odoo devuelve `[1, "SET IN SAS"]` → se guarda `1`; si viene `false` → `None`.

Log al resolver (una línea, sin URL ni base):
`🏭 Ubicación padre: 'Production' (Odoo ID: 12, empresa: 1)`

### 4c. `build_location_vals`

```python
def build_location_vals(nombre_saneado: str, production_id: int,
                        company_id: Optional[int] = None) -> Dict:
    vals = {
        "name": nombre_saneado,
        "location_id": production_id,
        "usage": _USAGE,
    }
    if company_id:
        vals["company_id"] = company_id
    return vals
```
Nunca se escribe `complete_name` (es computado por Odoo).

### 4d. `sync_one_location`

```python
def sync_one_location(client: OdooClient, proyecto: ProyectoLocal,
                      parent: ProductionParent, dry_run: bool = False
                      ) -> Tuple[Optional[int], str]:
    """Retorna (odoo_location_id, accion).
    accion ∈ {'created', 'sin_cambios', 'aviso', 'error'}."""
```

Secuencia exacta:

1. `nombre = sanitize_location_name(proyecto.nombre)`. Si queda vacío →
   `aviso`, sin llamar a Odoo.
2. **Búsqueda bajo el padre:**
   `[["name","=",nombre],["location_id","=",parent.id],["active","in",[True,False]]]`, `_SEARCH_FIELDS`, `limit=2`.
   - **2 resultados** → `aviso` ("duplicados en Odoo"), no se toca nada.
   - **1 resultado:**
     - `active` falso → `aviso` ("archivada en Odoo").
     - `usage != 'production'` → `aviso` (`usage` real en el mensaje).
     - resto → `sin_cambios`.
     - En los tres casos, si `proyecto.odoo_location_id != id_encontrado` y **no** es `dry_run`: `save_project_location_id(proyecto.nombre, id_encontrado)`.
3. **Búsqueda global** (solo si el paso 2 no encontró nada):
   `[["name","=",nombre],["active","in",[True,False]]]`, `limit=2`.
   - Hay resultados → `aviso`: "existe fuera de Production" + `complete_name`. **No se crea** (evita el duplicado) y **no** se guarda id local.
4. **Crear** (no apareció en ningún lado):
   - `dry_run=True` → log `  🆕 [DRY-RUN] Crearía ubicación: '<nombre>' bajo Production (ID 12)` y retorna `(None, "created")`.
   - `dry_run=False` → `client.create(_MODEL, build_location_vals(...))` → `save_project_location_id(...)` → `log_sync_action(proyecto_nombre=proyecto.nombre, odoo_model="stock.location", accion="created", odoo_id=nuevo_id, detalle=f"Creada bajo Production (ID {parent.id}) con nombre '{nombre}'")` → `(nuevo_id, "created")`.
5. `except OdooClientError as e` → log `error`, `log_sync_action(..., accion="error", detalle=str(e))`, retorna `(None, "error")`. **No corta la corrida**: el orquestador sigue con el próximo proyecto.

`log_sync_action` recibe siempre el nombre **original** en `proyecto_nombre` (para
poder cruzarlo con la tabla `proyectos`); el nombre saneado va en `detalle`.

### Formato exacto de los logs (para poder verificarlos con `grep`)

| Acción | Línea |
|---|---|
| creada | `  ✅ Ubicación creada: '<nombre>' (Odoo ID: <id>)` |
| dry-run creada | `  🆕 [DRY-RUN] Crearía ubicación: '<nombre>' bajo Production (ID <padre>)` |
| sin cambios | `  ➖ Ubicación ya existía: '<nombre>' (Odoo ID: <id>)` |
| aviso | `  ⚠️  Aviso en '<nombre>': <motivo>` |
| error | `  ❌ Error creando ubicación '<nombre>': <mensaje>` |

### No existe la acción `actualizado`

Si la ubicación se encontró por nombre, el nombre ya está bien (fue la clave de
búsqueda); padre, `usage` y `active` no se modifican nunca (decisión 3).

### Archivos que se borran en esta fase

`odoo-integration/sync_projects.py`, `odoo-integration/sync_tasks.py`
(con `git rm`, para que quede el rastro en el historial).

**Commit:** `feat(odoo): sync_locations.py crea ubicaciones de producción (Fase 4)`.

---

## Fase 5 — Orquestador + integración con el bot

**Estado:** ✅ Hecho

**Archivo:** `odoo-integration/odoo_sync.py`

### 5a. Firma

```python
def run_sync(dry_run: bool = False, only_projects: bool = False,
             ejecucion_id: Optional[int] = None,
             limit: Optional[int] = None) -> int:
```
- `ejecucion_id` presente → `get_ejecucion_inicio(ejecucion_id)`; si devuelve `None` → fatal, `return 1`.
- `ejecucion_id` ausente → `get_ultima_ejecucion_valida()`; si `None` → fatal con mensaje explícito, `return 1`. **Nunca** cae a "sincronizar todo".
- `only_projects` se conserva en la firma por compatibilidad: es **no-op** y loguea `ℹ️  --only-projects ya no tiene efecto (no se crean tareas).`
- `limit` → se aplica sobre la lista ya ordenada por nombre: `projects[:limit]`.

### 5b. Secuencia

1. `init_sync_table()` + `ensure_odoo_id_columns()` (igual que hoy, líneas 52-60; mismos `sys.exit(1)` por `FileNotFoundError`).
2. `OdooClient()` sin `allow_unconfigured`; `test_connection()` solo si **no** es `dry_run` (se conserva el comentario que explica por qué).
3. Resolver corrida (5a) y loguear: `📌 Corrida usada: #39 (inicio 2026-08-18T11:29:06.546841)`.
4. `resolve_production_location(client)`; `None` → fatal, `return 1`.
5. `get_projects_desde(inicio)`; lista vacía → warning explícito (`⚠️  La corrida #N no dejó proyectos para sincronizar.`) y `return 0`.
6. Loguear encabezado con **los dos números**: `📂 Proyectos de la corrida: 25 (BD local: 82)`. Con `limit`: `✂️  Límite activo: se procesan 1 de 25`.
7. Recorrido **plano** (ya no hay anidamiento proyecto→productos), `for i, proyecto in enumerate(projects, 1)`, línea `[i/total] Proyecto: '<nombre>'`.
8. Resumen y código de salida.

### 5c. Contadores

Se eliminan todos los `projects_*` y `tasks_*`. Quedan exactamente:
```python
stats = {"created": 0, "sin_cambios": 0, "aviso": 0, "error": 0}
```
Resumen final:
```
  Ubicaciones — Creadas: N, Sin cambios: N, Avisos: N, Errores: N
```
En `dry_run`, el encabezado del resumen dice `RESUMEN DE SIMULACIÓN (DRY-RUN)` y
"Creadas" se lee como "se crearían" (aclarado en la misma línea).

Código de salida: `2` si `stats["error"] > 0`, `1` en los fatales, `0` en el resto
(decisión 10).

### 5d. CLI

```
python odoo_sync.py                      # última corrida válida
python odoo_sync.py --dry-run            # simulación real (solo lecturas)
python odoo_sync.py --limit 1            # smoke test contra un solo proyecto
python odoo_sync.py --ejecucion-id 39    # corrida puntual
```
`--only-projects` se mantiene con `help` que aclara que es obsoleto.
Se actualiza el docstring del módulo y el `epilog` del `ArgumentParser`.

### 5e. Cambio en el bot

`scraper-fabricacion/main.py:416`:
```python
sync_exit_code = run_odoo_sync(dry_run=False, ejecucion_id=ejecucion_id)
```
`ejecucion_id` ya existe en ese scope (`main.py:219`). Agregar comentario de una
línea explicando que se pasa el id explícito porque en ese punto la corrida
todavía no tiene `timestamp_fin` (se cierra en el `finally`), así que la búsqueda
automática no la encontraría.

No se cambia nada más de `main.py`.

### Criterios de aceptación

- `grep -rn "sync_projects\|sync_tasks" --include=*.py .` → cero líneas.
- `python odoo_sync.py --help` muestra los 4 flags.
- Import limpio sin `.env` (lo que hace la CI): `python -c "import sys; sys.path.insert(0,'odoo-integration'); import odoo_sync"` no explota.

**Commit:** `refactor(odoo): orquestador de ubicaciones y baja de sync_projects/sync_tasks (Fase 5)`.

---

## Fase 6 — Verificación en simulación (`--dry-run`)

**Estado:** ✅ Hecho

El `--dry-run` viejo no consultaba nada (solo imprimía nombres). El nuevo:

- **Sí hace:** conectar, resolver corrida, resolver `Production`, buscar cada ubicación (bajo el padre y global). Todo `search_read`.
- **No hace:** `create`, `write`, ni `save_project_location_id`, ni `log_sync_action`.

### Ejecución y salida esperada hoy

```bash
cd odoo-integration
python odoo_sync.py --dry-run
```

| Métrica | Valor esperado |
|---|---|
| Corrida usada | #39 |
| Proyectos de la corrida | 25 (BD local: 82) |
| Padre | Production, ID 12 |
| Creadas (se crearían) | **24** |
| Sin cambios | **1** (`OP-CTOM-GAB-120826-0002`, Odoo ID 16) |
| Avisos | 0 |
| Errores | 0 |
| Código de salida | 0 |

Nota: `OP_ITC_Caja p/Baterias_1504261521` (el único nombre con `/`) **no** está
entre los 25 de la corrida 39, así que el saneo no se ejercita en esta corrida
real — se verifica con el test de regresión de la Fase 7.

### Prueba de que el dry-run no escribió nada

Antes y después de la corrida:
```bash
python -c "import sys; sys.path.insert(0,'odoo-integration'); import sqlite3, database_reader as d; c=sqlite3.connect(d.get_db_path()); print('con location_id:', c.execute('SELECT COUNT(*) FROM proyectos WHERE odoo_location_id IS NOT NULL').fetchone()[0]); print('log filas:', c.execute('SELECT COUNT(*) FROM odoo_sync_log').fetchone()[0])"
```
Los dos números deben ser **idénticos** antes y después (esperado: `0` y `3378`).
Y en Odoo, el total de `stock.location` sigue en 8.

**Commit:** `feat(odoo): dry-run con lecturas reales contra Odoo (Fase 6)`.

---

## Fase 7 — Pruebas automáticas

**Estado:** ✅ Hecho

`tests/test_odoo_builders.py` queda roto al borrarse `sync_projects.py` /
`sync_tasks.py`: se **elimina**. `tests/test_models.py` y `tests/test_parsing.py`
(lado scraper) no se tocan. `tests/conftest.py` no necesita cambios.

Las pruebas **no** hacen HTTP: usan un `FakeClient` local.

### `tests/test_odoo_locations.py` (nuevo)

`FakeClient` con la misma superficie que se usa de `OdooClient`:

```python
class FakeClient:
    def __init__(self, respuestas: dict, create_id: int = 999, fallar: bool = False): ...
    def search_read(self, model, domain, fields, limit=0) -> list: ...  # busca por (model, clave del domain)
    def create(self, model, vals) -> int: ...  # registra vals en self.creados, devuelve create_id
    def _call(self, model, method, body=None): ...  # no debería llamarse; assert
```
Debe **registrar** cada `search_read` (modelo + dominio) para poder afirmar sobre
el dominio usado, y `fallar=True` levanta `OdooClientError`.

Monkeypatch obligatorio en las pruebas que llegan a crear, para no tocar la BD real:
```python
monkeypatch.setattr("sync_locations.save_project_location_id", lambda *a, **k: None)
monkeypatch.setattr("sync_locations.log_sync_action", lambda *a, **k: None)
```

Casos:

| Clase | Test | Afirma |
|---|---|---|
| `TestSanitizeLocationName` | `test_nombre_real_con_barra` | `'OP_ITC_Caja p/Baterias_1504261521'` → `'OP_ITC_Caja p-Baterias_1504261521'` |
| | `test_multiples_barras` | `'a/b/c'` → `'a-b-c'` |
| | `test_recorta_espacios_de_los_bordes` | `'  OP_X  '` → `'OP_X'` |
| | `test_nombre_sin_barra_queda_igual` | `'OP-CTOM-GAB-120826-0002'` sin cambios |
| | `test_conserva_comillas_parentesis_y_punto` | `'OP_TOTEM_INC32"_2605260826'`, `'OP_TELECOM_MORSETOS26 (2)_1603260739'`, `'OP_VIALTRUCK_VOLCADORA9.3_2005260959'` sin cambios |
| `TestBuildLocationVals` | `test_campos_exactos` | `vals == {"name": ..., "location_id": 12, "usage": "production", "company_id": 1}` |
| | `test_sin_company_id_no_incluye_la_clave` | `"company_id" not in vals` |
| | `test_nunca_escribe_complete_name` | `"complete_name" not in vals` |
| `TestResolveProductionLocation` | `test_usa_xmlid_cuando_existe` | devuelve id del `res_id`; consultó `ir.model.data` |
| | `test_fallback_por_nombre_cuando_no_hay_xmlid` | devuelve id 12 |
| | `test_rechaza_sub_ubicacion_propia` | candidato con `location_id=[12,'Production']` → no se acepta |
| | `test_ambiguo_devuelve_none` | 2 candidatos `usage=production` sin padre → `None` |
| | `test_normaliza_company_id` | `[1,'SET IN SAS']` → `1`; `False` → `None` |
| `TestSyncOneLocation` | `test_crea_cuando_no_existe` | acción `created`, `client.creados` tiene 1 `vals` correcto |
| | `test_busca_con_el_nombre_saneado` (**regresión del duplicado**) | proyecto con `/`: el dominio de búsqueda contiene el nombre con `-`, y **no** el original |
| | `test_sin_cambios_cuando_ya_existe_igual` | acción `sin_cambios`, `client.creados == []` |
| | `test_aviso_si_usage_distinto` | acción `aviso`, sin `create` |
| | `test_aviso_si_esta_archivada` | acción `aviso` |
| | `test_aviso_si_hay_duplicados_bajo_el_padre` | acción `aviso` |
| | `test_aviso_si_existe_fuera_de_production` | acción `aviso`, sin `create` |
| | `test_dry_run_no_llama_create_ni_guarda` | acción `created`, `client.creados == []`, `save_project_location_id` nunca llamado (spy con lista) |
| | `test_error_de_odoo_devuelve_error` | `fallar=True` → acción `error`, no propaga la excepción |

### `tests/test_run_selection.py` (nuevo)

BD SQLite temporal (`tmp_path`) con `ejecuciones` y `proyectos` mínimas, apuntada
con `monkeypatch.setenv("DB_PATH", str(tmp_db))` — `database_reader._get_db_path()`
lee `os.getenv` en cada llamada, así que alcanza (usar ruta **absoluta**).

| Test | Escenario | Espera |
|---|---|---|
| `test_elige_la_ultima_terminada_con_proyectos` | corridas 1(ok), 2(`fin=NULL`), 3(ok) | id 3 |
| `test_ignora_corrida_sin_timestamp_fin` | única corrida con `fin=NULL` | `None` |
| `test_ignora_corrida_con_cero_proyectos` | `proyectos_procesados=0` con fin | `None` |
| `test_sin_corridas_devuelve_none` | tabla vacía | `None` |
| `test_get_ejecucion_inicio_sirve_para_corrida_abierta` | corrida con `fin=NULL` | devuelve su `timestamp_inicio` (no filtra por fin) |
| `test_get_ejecucion_inicio_id_inexistente` | id 999 | `None` |
| `test_get_projects_desde_filtra_por_fecha` | 3 proyectos, 2 posteriores al inicio | 2 |
| `test_get_projects_desde_incluye_proyecto_que_fallo_despues` | proyecto actualizado en la corrida pero no contado en `proyectos_procesados` | aparece en el resultado |
| `test_get_projects_desde_ordena_por_nombre` | nombres desordenados | orden alfabético |
| `test_get_projects_desde_trae_odoo_location_id` | fila con valor 16 | `ProyectoLocal.odoo_location_id == 16` |

### Criterios de aceptación

```bash
python -m pytest -q
```
verde, **sin `.env`** presente (así corre la CI: `.github/workflows/tests.yml`).
Ningún test hace red: `grep -rn "requests\|OdooClient()" tests/` no aparece en los
nuevos archivos. Cantidad de tests nuevos ≥ 28.

**Commit:** `test(odoo): pruebas de ubicaciones y de selección por corrida (Fase 7)`.

---

## Fase 8 — Documentación

**Estado:** ✅ Hecho

`README.md` — secciones a tocar (numeración actual del archivo):

| Sección | Cambio |
|---|---|
| §2 Arquitectura y flujo de datos | Diagrama nuevo: bot → BD → selección por corrida → `stock.location` |
| §3 Estructura de directorios | Sacar `sync_projects.py` / `sync_tasks.py`, agregar `sync_locations.py` y `scripts/manual_exploration/explorar_ubicaciones_odoo.py` |
| §4 Modelo de datos | `proyectos` con `odoo_location_id` (ER + tabla de detalle) |
| §6 Sincronizador con Odoo | Reescribir: modelo `stock.location`, resolución del padre, acciones `created/sin_cambios/aviso/error`, códigos de salida 0/1/2 |
| §7 Migraciones y cambios recientes | Entrada nueva de esta pasada (Fases 1-9) |
| §8 Guía de operación → Ejecución manual | Los 4 flags nuevos, y el orden recomendado: `--dry-run` → `--limit 1` → completo |
| §8 → Tests | Archivos de prueba nuevos |

Reglas: nada de credenciales, URLs internas ni usuario del ERP (ver commits
`e74d518`, `7cb72a7`). Este plan (`docs/plan_stock_locations.md`) se actualiza con
la tabla de estados en ✅.

**Commit:** `docs: README y plan al día con las ubicaciones de producción (Fase 8)`.

---

## Fase 9 — Corrida real (requiere aprobación explícita)

**Estado:** ⬜ Pendiente

**No ejecutar sin luz verde.** Crea registros en el Odoo de producción.

1. `python odoo_sync.py --limit 1` → crea **1** ubicación. Verificar:
   - log: `✅ Ubicación creada: '<nombre>' (Odoo ID: <id>)`
   - Odoo: total `stock.location` pasa de 8 a 9; el nuevo registro tiene `location_id=[12,'Production']`, `usage='production'`, `complete_name='Production/<nombre>'`.
   - BD local: 1 fila con `odoo_location_id` no nulo; `odoo_sync_log` +1 fila con `odoo_model='stock.location'`.
2. Reportar y **detenerse** para verificación.
3. Con la segunda luz verde: `python odoo_sync.py` (lote completo) → 24 creadas, 1 sin cambios (o 23/2 si el paso 1 ya creó una).
4. **Segunda corrida seguida, sin cambios de datos** — la prueba de idempotencia
   que caza el bug del duplicado: debe dar **0 creadas / 25 sin cambios**, y el
   total de `stock.location` en Odoo no puede moverse.

---

## Puntos críticos (revisar en cada verificación)

| Riesgo | Consecuencia | Mitigación | Cómo se comprueba |
|---|---|---|---|
| Saneo distinto al buscar y al crear | Duplica ubicaciones en cada corrida | Una sola función usada en los dos lados | `test_busca_con_el_nombre_saneado` + 2ª corrida con 0 creadas (Fase 9.4) |
| `Production` resuelta por `usage` a secas | Desde la 2ª corrida anida bajo una sub-ubicación nuestra | XML id primero; validación que rechaza candidatos cuyo padre es `Production` | `test_rechaza_sub_ubicacion_propia`; hoy hay 2 registros con `usage=production` (ids 12 y 16), así que el caso es real |
| Ubicación movida/renombrada a mano | Duplicado al no encontrarla bajo el padre | Segunda búsqueda global antes de crear | `test_aviso_si_existe_fuera_de_production` |
| Corrida suelta sin corrida válida | Confusión sobre qué se sincronizó | Corta con mensaje y código 1; nunca sincroniza todo | `test_sin_corridas_devuelve_none` |
| Bot cortado (0 procesados) | Sincroniza 0 en silencio | Log explícito `⚠️  La corrida #N no dejó proyectos...` | revisión del log en Fase 6 |
| `get_ejecucion_inicio` filtrando por `timestamp_fin` | El modo integrado nunca encuentra su propia corrida (se cierra recién en el `finally`) | Sin filtro de fin en esa función | `test_get_ejecucion_inicio_sirve_para_corrida_abierta` |
| Dry-run que escribe | Ensucia BD/Odoo "simulando" | Guardas explícitas en `sync_one_location` | conteos idénticos antes/después (Fase 6) |
| Credenciales en logs o docs | Filtración al pegar salidas | Nada de URL/base/API key/usuario en ninguna salida | revisión de `docs/fase1_recon_ubicaciones.md` y del reporte |

---

## Orden de ejecución y esfuerzo

`0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → [aprobación] → 9`

| Fase | Tiempo aprox. |
|---|---|
| 0-1 | 1 h |
| 2-3 | 1.5 h |
| 4 | 2 h |
| 5 | 1.5 h |
| 6 | 30 min |
| 7 | 2 h |
| 8 | 1 h |
| 9 | 30 min |
| **Total** | **~10 h** |
