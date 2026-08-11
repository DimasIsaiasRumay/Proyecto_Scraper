# Migración del Scraper a Estructura de 3 Niveles (Proyecto → Producto → Item) y Odoo

Este documento resume los cambios realizados para migrar el scraper y la base de datos de fabricación a una estructura jerárquica de 3 niveles, el borrado de tareas anteriores y la resincronización de productos como tareas en Odoo.

---

## Cambios Implementados

### 1. Modelos de Datos (`models.py`)
- Reemplazamos la clase plana `SubItem` por dos clases estructuradas:
  - `ProductoItem` (nivel 3): Contiene la información específica de sub-detalles o particiones de cada producto.
  - `Producto` (nivel 2): Contiene los datos del producto (nombre, cantidad, fechas, estado) y una lista de sus `items: List[ProductoItem]`.
- Modificamos `Proyecto` para que almacene una lista de `productos: List[Producto]` en lugar de subitems.

### 2. Base de Datos SQLite (`database.py`)
- Reemplazamos la tabla `proyecto_subitems` por dos tablas normalizadas:
  - `proyecto_productos`: Foto actual de cada producto (nivel 2). Con clave única `(proyecto_nombre, nombre)` y FK hacia `proyectos.nombre`.
  - `producto_items`: Foto actual de cada ítem hijo (nivel 3). Con clave única `(producto_id, nombre)` y FK hacia `proyecto_productos.id`.
- Creamos tablas de historial separadas:
  - `productos_historial_estados`: Historial de transiciones para productos.
  - `items_historial_estados`: Historial de transiciones para ítems individuales.
- Modificamos los métodos de inserción (`upsert_producto` y `upsert_item`) y las funciones de registro de historial para dar soporte a las nuevas tablas relacionales.

### 3. Extractor Web (`scraper.py`)
- Actualizamos la función `extraer_proyectos` para identificar el parentesco de las filas dinámicas de la tabla de proyectos usando sus atributos `data-tt-id` y `data-tt-parent-id`.
- Si `data-tt-parent-id` es nulo, se registra como **Proyecto** (nivel 1).
- Si `data-tt-parent-id` apunta al ID de un proyecto padre, se registra como **Producto** (nivel 2).
- Si `data-tt-parent-id` apunta al ID de un producto, se registra como **Item** (nivel 3) y se agrega al producto correspondiente.

### 4. Orquestador (`main.py`)
- Actualizamos el flujo de ejecución principal para recorrer y guardar la jerarquía completa: primero el Proyecto, luego sus Productos, y finalmente los Items de cada Producto (usando el ID generado por la base de datos para la relación de clave foránea).

### 5. Integración con Odoo (`odoo-integration/`)
- **Limpieza de Tareas Existentes**: Ejecutamos un script automatizado que vació todas las tareas existentes de Odoo (`project.task`) de forma segura en lotes de 100, manteniendo intactos los proyectos correspondientes.
- **Sincronización de Productos**: Modificamos los scripts `odoo_sync.py`, `sync_tasks.py` y `database_reader.py` para leer y sincronizar los registros de la tabla `proyecto_productos` como tareas en Odoo (ignorando los ítems de nivel 3).
- **Esquema de Log de Sincronización**: Actualizamos `sync_logger.py` para utilizar columnas y nombres de parámetros orientados a productos (`producto_nombre`) en lugar de subitems.
- **Versión de Python**: Modificamos el lanzador rápido `run_sync.bat` para que ejecute la sincronización bajo el intérprete de `py -3.10` para garantizar compatibilidad de módulos.

### 6. Archivo de Pruebas (`test/test_db_history.py`)
- Adaptamos el script de verificación para manipular el estado de un producto (nivel 2) y validar que el historial registre de forma correcta los cambios de estado en la nueva tabla `productos_historial_estados`.

---

## Verificación de Resultados de Pruebas

1. **Prueba de Extracción y Poblado de 3 Niveles:**
   - Eliminamos la base de datos `fabricacion.db` bloqueada por el usuario (liberando el bloqueo de *DB Browser for SQLite*).
   - Ejecutamos el bot en modo test (`py -3.10 scraper-fabricacion/main.py --force --test`). El bot completó la extracción de los primeros 3 proyectos:
     - **3 Proyectos** creados en DB.
     - **15 Productos** creados en la tabla `proyecto_productos`.
     - **275 Items** creados en la tabla `producto_items` (correctamente enlazados vía `producto_id` de clave foránea).
     - **111 Materiales** creados en la tabla `materiales`.

2. **Prueba de Historial de Estados:**
   - Corrimos el script `test_db_history.py` el cual simuló un cambio de estado manual en DB a un proyecto y un producto.
   - Tras correr el scraper, este detectó la diferencia y guardó las transiciones en el historial:
     - `proyectos_historial_estados`: 1 registro (`Test Modificado` → `Material OK`).
     - `productos_historial_estados`: 1 registro (`Test Modificado` → `En Pintura/Galvanizado (A)`).

3. **Prueba de Sincronización con Odoo:**
   - La corrida de sincronización en Odoo se completó exitosamente:
     - Modificó y actualizó los 3 proyectos activos en Odoo.
     - Creó **15 nuevas tareas** (correspondientes a los 15 Productos locales de la DB SQLite) y enlazó sus identificadores de vuelta en la base de datos local en la columna `odoo_id` de la tabla `proyecto_productos`.
