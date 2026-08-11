# Checklist de Tareas — Bot Scraper de Fabricación (Estructura de 3 Niveles y Odoo)

- [x] Borrado de tareas anteriores en Odoo (`project.task`) de forma segura en lotes
- [x] Modificación de modelos de datos en `models.py` (adición de `Producto` y `ProductoItem`)
- [x] Actualización de la estructura de base de datos SQLite en `database.py` (tablas `proyecto_productos` y `producto_items`)
- [x] Adaptación de la lógica de extracción del árbol en `scraper.py` (detección de 3 niveles)
- [x] Actualización de la lógica del orquestador en `main.py`
- [x] Actualización del lector de base de datos y scripts de sincronización de Odoo para enlazar Productos (como tareas) y guardar IDs de Odoo locales
- [x] Ajuste de scripts de prueba (`test_db_history.py`) para utilizar las nuevas tablas
- [x] Re-población de la base de datos local desde cero (ejecución exitosa del scraper en modo de prueba)
- [x] Sincronización en vivo exitosa de Productos en Odoo
