# Plan: Fallback a "Editar Formulario" para proyectos con detalle roto

> Cuando `Visualizar Detalle` no carga (falla de backend del ERP), reintentar la
> extracción abriendo `Editar Formulario` **en modo estrictamente de solo lectura**.
> Incluye además una corrección independiente: eliminar el re-login redundante en
> los reintentos.
>
> **Plan de ejecución exacto.** Define archivo por archivo, firma por firma y
> criterio de aceptación por fase. Se actualiza en vivo.

## Estado general

| Fase | Descripción | Estado |
|---|---|---|
| 0 | Preparación (rama, baseline verde) | ✅ Hecho |
| 1 | Quick win: sacar re-login redundante | ✅ Hecho |
| 2 | Reconocimiento DOM comparado (solo lectura) | ⬜ Pendiente |
| 3 | Lector de campos agnóstico al tipo de elemento | ⬜ Pendiente |
| 4 | Fallback en `extraer_materiales()` | ⬜ Pendiente |
| 5 | Guardas anti-escritura | ⬜ Pendiente |
| 6 | Validación en `--dry-run` contra el ERP | ⬜ Pendiente |
| 7 | Pruebas automáticas | ⬜ Pendiente |
| 8 | Documentación | ⬜ Pendiente |
| 9 | Corrida real sobre los 2 proyectos rotos | ⬜ Pendiente |

Marcadores: ⬜ Pendiente · 🔄 En curso · ✅ Hecho · ⏸️ Bloqueado

---

## Problema

Corrida del 18/08/2026 (ejecución id **39**, 11:29–11:50). Dos proyectos fallaron:

| Proyecto | Síntoma | Desde |
|---|---|---|
| `OP-ING-EPLIQ-070826-0001` | Timeout 20s esperando `#detalleProyecto table`, 3 reintentos | 18/08/2026 |
| `OP_CLARO_Complemento COWRoja_2906261616` | Idéntico | **30/06/2026** (recurrente, ~2 meses) |

Confirmado por el usuario desde la UI: `Visualizar Detalle` **no carga para ninguno
de los dos**. `Editar Formulario` (ícono a la derecha, misma celda de Acciones)
**sí muestra los materiales**.

Causa raíz: falla de backend del ERP al renderizar el detalle, no un selector roto
del scraper. Ya documentada en [`scraper.py:415-423`](../scraper-fabricacion/scraper.py).

---

## Datos verificados antes de planificar

### BD local (`scraper-fabricacion/data/fabricacion.db`) — consulta real

Total materiales: **942**. Campos no nulos / no vacíos:

| Campo | Patrón DOM (`item`) | No nulos | Lectura actual |
|---|---|---|---|
| `cantidad` | `#cant_{mid}` | 942/942 | `inner_text()` |
| `stock_chapa_barras` | `#stock_{mid}` | 942/942 | `inner_text()` |
| `estado_compra` | `#estado_compra_{mid}` | 942/942 | `inner_text()` |
| `precio_sw` | `#precio_actual_{mid}` | 909/942 | `inner_text()` |
| `comentarios` | `#comentario_{mid}` | 460/942 | `inner_text()` |
| `validacion_diseno` | `#val_dis_{mid}` | 421/942 | `inner_text()` |

### Contradicción a resolver en Fase 2 (bloqueante)

En la captura del formulario, `Validacion Diseño`, `Stock`, `Precio SW`,
`Precio Compra` y `Comentarios` aparecen como **cajas con borde** (inputs), y
`Estado Compra` como **`<select>`**.

Pero `inner_text()` sobre un `<input>` devuelve **siempre cadena vacía** — y aun
así esos campos hoy traen datos reales de la vista `Visualizar Detalle`.

Conclusión: **la estructura visual coincide, pero los tipos de elemento del DOM
probablemente no.** Esto no se puede asumir: se mide en Fase 2 antes de escribir
una línea del fallback.

### Riesgo que esto genera (motivo de la Fase 3)

Si el formulario usa `<input>` donde el detalle usa texto, y se reutiliza
`extraer_materiales_de_seccion()` tal cual:

1. `inner_text()` devuelve `""` — **sin lanzar excepción**
2. `parse_float("")` devuelve `None` en la primera línea, **sin loguear warning**
   ([`parsing.py:52-54`](../scraper-fabricacion/parsing.py))
3. Los materiales se guardan con todos los campos numéricos en `NULL`
4. La corrida reporta ✅ éxito

Se cambiaría un error ruidoso por una **corrupción silenciosa de datos**. Es el
riesgo principal del plan y la razón de que la Fase 3 exista.

---

## Fase 0 — Preparación

**Objetivo:** partir de un baseline verde y aislado.

1. Crear rama `feat/fallback-formulario` desde `main`.
2. Correr la suite existente: `python -m pytest tests/ -v`. Debe quedar en verde
   **antes** de tocar nada.
3. Respaldar la BD: copia de `scraper-fabricacion/data/fabricacion.db` a
   `data/fabricacion.db.bak-preformulario`.

**Aceptación:** suite en verde, rama creada, backup existente.

---

## Fase 1 — Quick win: eliminar el re-login redundante

**Objetivo:** aplicar la corrección del usuario. Es independiente del fallback y
no tiene riesgo, así que va primero.

**Archivo:** [`scraper-fabricacion/main.py:339-342`](../scraper-fabricacion/main.py)

Hoy, en cada reintento por timeout:

```python
try:
    login(page)
except Exception:
    pass
```

Ese `login()` hace re-autenticación completa (navega al login, tipea usuario y
contraseña con delays humanos, valida). Costo medido en el log del 18/08:
**~7 s por reintento, ~14 s por proyecto fallido**.

Es redundante por tres razones acumuladas:

1. `check_session_and_relogin(page)` ya se llama al inicio de cada reintento
   (`main.py:307`)
2. Y otra vez al entrar a `extraer_materiales()` (`scraper.py:361`)
3. Y lo primero que hace `extraer_materiales()` es `page.goto(URL_MATERIALES)`
   (`scraper.py:363`) — navegación fresca completa, más fuerte que un F5, que ya
   limpia el overlay `.jquery-loading-modal` atascado

**Cambio:** reemplazar el bloque por `page.reload()` envuelto en `try/except`, o
eliminarlo. Se opta por `page.reload()` para conservar el gesto explícito de
"refrescar" que el usuario validó a mano en la UI.

**Aceptación:** el log de una corrida de prueba ya no muestra
`Intentando iniciar sesión...` entre reintentos de un mismo proyecto; la sesión
se mantiene y el proyecto se procesa igual.

### Resultado real (19/08/2026)

Cambio aplicado en `main.py:339-354` — se reemplazó `login(page)` por
`page.reload(timeout=config.TIMEOUT_NAV)` dentro del mismo `try/except`, con
comentario explicando por qué es seguro (mismo razonamiento de la sección de
arriba). Suite completa: **60/60 passed**. `login` sigue importado y en uso
(login inicial de la corrida, línea 267). Aún no verificado en una corrida real
contra el ERP — queda pendiente de observar en la Fase 9, cuando se corra sobre
los proyectos rotos.

---

## Fase 2 — Reconocimiento DOM comparado (solo lectura) 🔑

**Objetivo:** resolver empíricamente la contradicción de arriba. **Fase
bloqueante:** sin sus resultados, las fases 3 y 4 no se pueden escribir.

**Archivo nuevo:** `scripts/manual_exploration/explorar_formulario_edicion.py`
(sigue el patrón ya existente de `test_scrape_live.py` / `test_scrape_suministros.py`)

El script **solo lee y vuelca HTML**. No escribe en la BD ni en el ERP.

### Paso 2.1 — Comparar ambas vistas en un proyecto que SÍ funciona

Proyecto de referencia: **`OP-AMX-EMIX-070826-0001`** (procesado OK el 18/08:
4 items, 2 suministros; es el de la captura).

Para ese proyecto, volcar a disco:

- `dump_detalle_OP-AMX-EMIX.html` — DOM tras `Visualizar Detalle`
- `dump_formulario_OP-AMX-EMIX.html` — DOM tras `Editar Formulario`

Y para cada uno de los 12 campos de `MATERIAL_ID_PATTERNS`, reportar en tabla:

| Campo | ID resuelto | ¿Existe? | `tagName` | `inner_text()` | `input_value()` |
|---|---|---|---|---|---|

Esto responde de una las tres preguntas que trancan todo:

1. ¿Los IDs (`#cant_{mid}`, `#suministro_stock_{mid}`, …) son **los mismos** en
   ambas vistas?
2. ¿Existen `#hdnItemsId` y `#hdnSuministrosId` en el formulario? (son la fuente
   de los IDs de material — `scraper.py:450-454`)
3. ¿Qué `tagName` tiene cada campo en cada vista, y cuál de los dos métodos
   devuelve el valor real?

### Paso 2.2 — Verificar que el formulario carga en los proyectos rotos

Repetir el volcado sobre `OP_CLARO_Complemento COWRoja_2906261616` y
`OP-ING-EPLIQ-070826-0001`.

Confirmar: el formulario carga, y los IDs de material que expone coinciden con
los del paso 2.1.

### Paso 2.3 — Detectar efectos colaterales de abrir el formulario

Mientras el script corre, registrar:

- ¿El ERP dispara alguna petición `POST` al abrir el formulario? (capturar tráfico
  de red con `page.on("request")`)
- ¿Aparece algún indicador de bloqueo/lock del registro?
- Tras salir con `page.goto(URL_MATERIALES)`, ¿los datos del proyecto siguen
  intactos? Verificar a mano en la UI contra los valores previos.

**Aceptación:** tabla de los 12 campos × 2 vistas completa, volcados HTML en
disco, confirmación de que el formulario carga en los 2 proyectos rotos, y
constancia de que abrir el formulario no dispara escrituras.

> **Punto de decisión.** Si el paso 2.3 detecta escrituras o locks, el plan se
> detiene acá y se reevalúa. Si el paso 2.2 muestra que el formulario tampoco
> carga en los proyectos rotos, el plan se cancela y se escala el problema al
> proveedor del ERP.

---

## Fase 3 — Lector de campos agnóstico al tipo de elemento

**Objetivo:** que la extracción funcione con `<span>`, `<td>`, `<input>` o
`<select>` sin duplicar la lógica ni corromper datos en silencio.

**Archivo:** [`scraper-fabricacion/scraper.py`](../scraper-fabricacion/scraper.py)

Función nueva:

```python
def _leer_valor_campo(page: Page, selector: str) -> str:
    """Lee el valor de un campo sin importar si es texto, <input> o <select>.

    Solo lectura: no dispara eventos onchange/onblur del JS del ERP.
    """
```

Reglas:

- `tagName` = `INPUT` o `TEXTAREA` → `input_value()`
- `tagName` = `SELECT` → texto de la opción seleccionada
- Resto → `inner_text()`
- Elemento inexistente → devuelve `""` **y loguea un warning explícito** (para
  que un cambio de estructura del ERP no vuelva a pasar callado)

`extraer_materiales_de_seccion()` pasa a usar este helper en vez de llamar
`inner_text()` directo (`scraper.py:321`). El comportamiento sobre la vista
`Visualizar Detalle` **no cambia**: los campos de texto siguen leyéndose igual.

**Aceptación:** una corrida normal sobre un proyecto sano produce **exactamente
los mismos valores** que antes del cambio (comparación campo a campo contra la BD).

---

## Fase 4 — Fallback en `extraer_materiales()`

**Objetivo:** usar el formulario cuando el detalle se agota, sin tocar el camino
feliz.

**Archivo:** [`scraper-fabricacion/scraper.py:424-446`](../scraper-fabricacion/scraper.py)

**Punto de inserción exacto:** el `raise` de la línea 446, que hoy se dispara al
agotar `MAX_INTENTOS_DETALLE`. Los 23 proyectos que hoy funcionan **no ejecutan
ni una línea nueva**.

Estructura resultante:

```
intento 1: Visualizar Detalle          (sin cambios)
intento 2: Visualizar Detalle          (sin cambios, limpia .jquery-loading-modal)
    ↓ ambos agotados
NUEVO: Editar Formulario (solo lectura) ← fallback
    ↓ también falla
raise PlaywrightTimeoutError            (comportamiento actual, intacto)
```

Función nueva:

```python
def _abrir_formulario_edicion(page: Page, target_row: Locator, proyecto_nombre: str) -> bool:
    """Abre 'Editar Formulario' como fallback de 'Visualizar Detalle'.

    SOLO LECTURA. Devuelve True si la tabla de materiales quedó cargada.
    """
```

Logging obligatorio: cuando un proyecto se extraiga por esta vía, el log debe
decirlo de forma inequívoca, p. ej.
`Proyecto 'X': detalle no disponible, extraído vía formulario de edición (solo lectura).`
Nunca debe quedar indistinguible de una extracción normal.

**Aceptación:** los 2 proyectos rotos se extraen con materiales; los 23 sanos
siguen usando el camino de siempre (verificable en el log).

---

## Fase 5 — Guardas anti-escritura

**Objetivo:** garantía técnica, no solo disciplina, de que nunca se modifica el ERP.

Reglas duras dentro de la rama del formulario:

| Prohibido | Permitido |
|---|---|
| `fill()`, `type()`, `select_option()`, `check()`, `press()` | `input_value()` |
| `click()` sobre cualquier control del formulario | `get_attribute("value")` |
| `page.go_back()` para salir (riesgo de autosave al abandonar) | `inner_text()` |
| Cualquier submit | `page.goto(URL_MATERIALES)` para salir limpio |

Medidas concretas:

1. **Salida limpia:** siempre `page.goto(URL_MATERIALES)`, nunca `go_back()`.
2. **Detector de escrituras:** registrar un handler `page.on("request")` activo
   mientras el formulario está abierto. Si detecta un `POST`/`PUT` hacia el ERP,
   loguear `ERROR` visible y abortar ese proyecto.
3. **Comentario de bloque** en el código explicando por qué esa rama es de solo
   lectura, en el mismo estilo del comentario ya existente en `scraper.py:415-423`.

**Aceptación:** revisión de código confirma que no existe ninguna llamada de
escritura de Playwright dentro de la rama; el detector no registra `POST` durante
una corrida completa.

---

## Fase 6 — Validación en `--dry-run` contra el ERP

**Objetivo:** verificar los datos extraídos **antes** de que toquen la BD.

Flag nuevo en `main.py`: `--dry-run-formulario`. Con él, el fallback extrae y
**loguea** los materiales, pero **no llama a `upsert_material()`**.

Procedimiento:

1. Correr con el flag sobre `OP_CLARO_Complemento COWRoja_2906261616`.
2. Abrir el mismo proyecto en la UI del ERP.
3. Comparar **campo a campo, material por material**, lo logueado contra lo que
   muestra la pantalla.
4. Prestar atención especial a los campos que en la captura son inputs/selects:
   `Validacion Diseño`, `Stock`, `Precio SW`, `Precio Compra`, `Estado Compra`,
   `Comentarios`.

**Criterio de rechazo:** si algún campo numérico llega vacío o en `0` cuando la
UI muestra un valor, **el fallback no pasa**. Es exactamente el modo de falla
silenciosa que el plan busca evitar.

**Aceptación:** coincidencia 100 % entre lo logueado y la UI, verificada a mano.

---

## Fase 7 — Pruebas automáticas

**Archivo nuevo:** `tests/test_lectura_campos.py`

Cobertura, con HTML de fixture tomado de los volcados reales de la Fase 2 (sin
tocar el ERP ni la red):

| Caso | Espera |
|---|---|
| `_leer_valor_campo` sobre `<span>` | devuelve el texto |
| `_leer_valor_campo` sobre `<input value="101.76">` | devuelve `"101.76"` |
| `_leer_valor_campo` sobre `<select>` con opción elegida | devuelve el texto de la opción |
| `_leer_valor_campo` sobre elemento inexistente | devuelve `""` **y loguea warning** |
| Regresión: `parse_float("")` | sigue devolviendo `None` (documenta el riesgo) |

Además, la suite completa (`tests/`) debe seguir en verde.

**Aceptación:** `python -m pytest tests/ -v` en verde, casos nuevos incluidos.

---

## Fase 8 — Documentación

1. Actualizar `README.md`: sección sobre el fallback, con la advertencia de solo
   lectura bien visible.
2. Actualizar este plan con los resultados reales de cada fase (igual que
   `plan_stock_locations.md`).
3. Registrar en el plan la tabla de reconocimiento de la Fase 2, para que si el
   ERP cambia se pueda comparar contra la referencia.

---

## Fase 9 — Corrida real

1. Corrida acotada sobre los 2 proyectos rotos, **sin** `--dry-run`.
2. Verificar en la BD que los materiales quedaron con valores correctos
   (comparar contra lo validado en la Fase 6).
3. Verificar en la UI del ERP que **nada cambió** en esos proyectos.
4. Corrida completa de las 25 ubicaciones.
5. Confirmar en el log: `Proyectos fallidos: 0` (o solo
   `OP_TELECOM_BANQUINAS_1414260913`, que es omisión legítima por no tener
   materiales cargados en el ERP, no un error).

**Aceptación:** los 2 proyectos históricamente rotos quedan procesados, el ERP
sin modificaciones, y la corrida completa sin fallos nuevos.

---

## Resumen de archivos tocados

| Archivo | Fase | Tipo |
|---|---|---|
| `scraper-fabricacion/main.py` | 1, 6 | Modificación menor |
| `scripts/manual_exploration/explorar_formulario_edicion.py` | 2 | **Nuevo** (solo lectura) |
| `scraper-fabricacion/scraper.py` | 3, 4, 5 | Modificación (aditiva) |
| `tests/test_lectura_campos.py` | 7 | **Nuevo** |
| `README.md` | 8 | Documentación |
| `docs/plan_fallback_formulario.md` | 8 | Este documento |

**No se toca:** `database.py`, `models.py`, `parsing.py`, `config.py`, ni nada de
`odoo-integration/`. La sincronización con Odoo funciona y queda fuera de alcance.

---

## Riesgos abiertos

| Riesgo | Mitigación | Fase |
|---|---|---|
| El formulario usa IDs distintos a los del detalle | Reconocimiento previo obligatorio | 2 |
| Lectura silenciosa de campos vacíos que corrompe la BD | Lector agnóstico + validación manual en dry-run | 3, 6 |
| Abrir el formulario modifica o bloquea datos del ERP | Guardas duras + detector de `POST` + verificación en UI | 5, 9 |
| El formulario tampoco carga en los proyectos rotos | Se detecta en Fase 2; plan se cancela y se escala al proveedor | 2 |
| El fallback enmascara una falla real del ERP | Logging explícito diferenciado en cada extracción por formulario | 4 |
