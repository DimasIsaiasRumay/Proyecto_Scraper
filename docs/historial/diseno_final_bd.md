# Esquema de base de datos final
┌─────────────────────────────────────────────────────────────────┐
│                        PROYECTOS                                │
├─────────────────────────────────────────────────────────────────┤
│ proyectos                    → estado actual del proyecto padre │
│ proyecto_productos           → estado actual de cada Producto   │
│ producto_items               → estado actual de cada Item       │
│ proyectos_historial_estados  → cambios de estado del padre      │
│ productos_historial_estados  → cambios de estado de Productos   │
│ items_historial_estados      │ cambios de estado de Items       │
├─────────────────────────────────────────────────────────────────┤
│                        MATERIALES                               │
├─────────────────────────────────────────────────────────────────┤
│ materiales                   → estado actual de cada material   │
│ materiales_historial_estados → cambios de estado compra         │
├─────────────────────────────────────────────────────────────────┤
│                        SISTEMA                                  │
├─────────────────────────────────────────────────────────────────┤
│ ejecuciones                  → log de cada corrida              │
│ checkpoint                   → punto de reanudación ante fallo  │
└─────────────────────────────────────────────────────────────────┘

# Detalle de cada tabla
`proyectos` — foto actual del proyecto padre
nombre                TEXT  PRIMARY KEY   ← "OP_CLIENTE_A_BANDEJA_SOLAR_..."
cliente               TEXT
estado                TEXT               ← "Material OK", "Cerrado"...
fecha_primera_carga   DATETIME
fecha_ultima_sync     DATETIME

`proyecto_productos` — foto actual de cada producto (nivel 2)
id                    INTEGER PRIMARY KEY AUTOINCREMENT
proyecto_nombre       TEXT    FK → proyectos.nombre ON DELETE CASCADE
nombre                TEXT               ← "bandeja solar", "brazo izaje"...
cantidad              REAL
solicitud             DATE
entrega_fc            DATE
entrega               DATE
estado                TEXT               ← "En Fabricación", "En Pintura"...
fecha_primera_carga   DATETIME
fecha_ultima_sync     DATETIME
UNIQUE (proyecto_nombre, nombre)

`producto_items` — foto actual de cada ítem hijo del producto (nivel 3)
id                    INTEGER PRIMARY KEY AUTOINCREMENT
producto_id           INTEGER FK → proyecto_productos.id ON DELETE CASCADE
nombre                TEXT               ← sub-detalle o división del producto...
cantidad              REAL
solicitud             DATE
entrega_fc            DATE
entrega               DATE
estado                TEXT
fecha_primera_carga   DATETIME
fecha_ultima_sync     DATETIME
UNIQUE (producto_id, nombre)

`proyectos_historial_estados` — cada vez que el padre cambia de estado
id                INTEGER  PRIMARY KEY AUTOINCREMENT
proyecto_nombre   TEXT     FK → proyectos.nombre
estado_anterior   TEXT
estado_nuevo      TEXT
fecha_cambio      DATETIME

`productos_historial_estados` — cada vez que un producto cambia de estado
id                INTEGER  PRIMARY KEY AUTOINCREMENT
proyecto_nombre   TEXT
producto_nombre   TEXT
estado_anterior   TEXT
estado_nuevo      TEXT
fecha_cambio      DATETIME

`items_historial_estados` — cada vez que un ítem cambia de estado
id                INTEGER  PRIMARY KEY AUTOINCREMENT
producto_id       INTEGER  FK → proyecto_productos.id
item_nombre       TEXT
estado_anterior   TEXT
estado_nuevo      TEXT
fecha_cambio      DATETIME

`materiales` — foto actual de cada material (Item y Suministro)
id                  INTEGER  PRIMARY KEY AUTOINCREMENT
proyecto_nombre     TEXT     FK → proyectos.nombre
tipo                TEXT     ← "item" | "suministro"
codigo_mp           TEXT               ← "MP_0414"
descripcion         TEXT
proveedor           TEXT
cantidad            REAL
desperdicio_12      REAL
validacion_diseno   REAL
stock_chapa_barras  REAL
comprar             REAL
precio_sw           REAL
precio_compra       REAL
orden_compra        TEXT
numero_factura      TEXT
estado_compra       TEXT               ← "OC Enviada", "En Set IN"...
comentarios         TEXT
fecha_primera_carga DATETIME
fecha_ultima_sync   DATETIME
UNIQUE (proyecto_nombre, tipo, codigo_mp)

`materiales_historial_estados` — cada vez que cambia estado_compra
id                INTEGER  PRIMARY KEY AUTOINCREMENT
proyecto_nombre   TEXT
codigo_mp         TEXT
tipo              TEXT
estado_anterior   TEXT
estado_nuevo      TEXT
fecha_cambio      DATETIME

`ejecuciones` — log estructurado de cada corrida
id                      INTEGER  PRIMARY KEY AUTOINCREMENT
timestamp_inicio        DATETIME
timestamp_fin           DATETIME
estado                  TEXT     ← "ok" | "parcial" | "error"
proyectos_procesados    INTEGER
materiales_procesados   INTEGER
mensaje_error           TEXT

`checkpoint` — reanudación ante fallo (una sola fila activa)
id                          INTEGER PRIMARY KEY
ejecucion_id                INTEGER  FK → ejecuciones.id
ultimo_proyecto_procesado   TEXT
timestamp                   DATETIME

# Flujo de decisión por corrida
INICIO
  │
  ├─► ¿Hay checkpoint activo? ──SÍ──► Retomar desde último proyecto
  │                                    procesado
  └─► NO ──► Arrancar desde el principio
  
POR CADA PROYECTO:
  │
  ├─► ¿Existe en tabla proyectos?
  │     NO  ──► INSERT + INSERT materiales
  │     SÍ  ──► ¿Cambió estado padre?    ──SÍ──► INSERT historial
  │             ¿Cambió estado producto? ──SÍ──► INSERT historial
  │             ¿Cambió estado ítem?     ──SÍ──► INSERT historial
  │             ¿Cambió estado material? ──SÍ──► INSERT historial
  │             UPDATE fecha_ultima_sync en todos
  │
  └─► Actualizar checkpoint

FIN ──► Marcar ejecución como "ok", borrar checkpoint

# Estructura de archivos final
scraper-fabricacion/
│
├── main.py          ← orquesta todo, maneja lock anti-solapamiento
├── scraper.py       ← Playwright: login, navegación, extracción
├── database.py      ← todas las operaciones SQLite (ahora con 3 niveles)
├── models.py        ← dataclasses: Proyecto, Producto, ProductoItem, Material
├── config.py        ← URL, credenciales, tiempos de espera
├── logs/
│   └── scraper.log  ← rotativo, máx 5MB x 3 archivos
├── data/
│   └── fabricacion.db  ← SQLite
└── requirements.txt