# sync_tasks.py — Sincronización de productos como tareas en Odoo (project.task)
"""
Lógica de upsert para el modelo project.task de Odoo.
Cada producto de la BD local se mapea a una tarea dentro del proyecto Odoo correspondiente.
Estrategia de búsqueda:
  1. Si el producto tiene odoo_id guardado en la BD local → buscar por ID (rápido)
  2. Si no → buscar por nombre + project_id (fallback)
Tras crear/actualizar, guarda el odoo_id en la BD local.
"""

import logging
from typing import Dict, Optional, Tuple

from odoo_client import OdooClient, OdooClientError
from sync_logger import log_sync_action
from database_reader import save_producto_odoo_id
from odoo_models import ProductoLocal

logger = logging.getLogger("odoo_sync")

# Campos que se leen de Odoo para verificar existencia
_SEARCH_FIELDS = ["id", "name", "date_deadline"]


def _build_task_vals(producto: ProductoLocal, project_odoo_id: int) -> Dict:
    """
    Construye el diccionario de valores para crear/actualizar una tarea en Odoo.
    Mapea los campos de ProductoLocal a project.task (acceso por atributo).
    """
    vals = {
        "name": producto.nombre,
        "project_id": project_odoo_id,
    }

    # Descripción con información del estado y cantidades
    description_parts = []
    if producto.estado:
        description_parts.append(f"Estado: {producto.estado}")
    if producto.cantidad is not None:
        description_parts.append(f"Cantidad: {producto.cantidad}")
    if producto.solicitud:
        description_parts.append(f"Solicitud: {producto.solicitud}")
    if producto.entrega_fc:
        description_parts.append(f"Entrega FC: {producto.entrega_fc}")

    if description_parts:
        vals["description"] = " | ".join(description_parts)

    # Fecha de entrega → deadline de la tarea (si existe)
    if producto.entrega:
        vals["date_deadline"] = producto.entrega

    return vals


def sync_one_task(
    client: OdooClient,
    producto: ProductoLocal,
    project_odoo_id: int,
    proyecto_nombre: str,
    dry_run: bool = False,
) -> Tuple[Optional[int], str]:
    """
    Sincroniza un producto individual como tarea en Odoo.

    Parámetros:
        client: Instancia de OdooClient.
        producto: ProductoLocal (nombre, estado, cantidad, solicitud, odoo_id, etc.).
        project_odoo_id: ID del proyecto padre en Odoo.
        proyecto_nombre: Nombre del proyecto padre (para logging y guardado de odoo_id).
        dry_run: Si True, no hace cambios en Odoo.

    Retorna:
        (odoo_task_id, accion) donde accion es 'created', 'updated', 'skipped', o 'error'.
    """
    producto_nombre = producto.nombre
    local_odoo_id = producto.odoo_id
    vals = _build_task_vals(producto, project_odoo_id)

    # En modo dry-run, no hacer ninguna llamada a Odoo
    if dry_run:
        if local_odoo_id:
            logger.info(
                f"    [DRY-RUN] Actualizaría tarea '{producto_nombre}' "
                f"(Odoo ID local: {local_odoo_id})"
            )
        else:
            logger.info(
                f"    [DRY-RUN] Sincronizaría tarea '{producto_nombre}' "
                f"en proyecto '{proyecto_nombre}'"
            )
        return local_odoo_id, "skipped"

    try:
        existing = None

        # 1. Si tenemos odoo_id guardado, verificar que siga existiendo en Odoo
        if local_odoo_id:
            try:
                check = client.search_read(
                    "project.task",
                    [["id", "=", local_odoo_id]],
                    ["id"],
                    limit=1,
                )
                if check:
                    existing = check
            except OdooClientError:
                pass

        # 2. Fallback: buscar por nombre + proyecto
        if not existing:
            existing = client.search_read(
                "project.task",
                [
                    ["name", "=", producto_nombre],
                    ["project_id", "=", project_odoo_id],
                ],
                _SEARCH_FIELDS,
                limit=1,
            )

        if existing:
            # Tarea ya existe → actualizar
            task_id = existing[0]["id"]

            # No enviar project_id en el write (no se cambia el padre)
            write_vals = {k: v for k, v in vals.items() if k != "project_id"}
            client.write("project.task", task_id, write_vals)

            logger.info(
                f"    ✏️  Tarea actualizada: '{producto_nombre}' "
                f"(Odoo ID: {task_id})"
            )

            # Guardar odoo_id en BD local
            save_producto_odoo_id(proyecto_nombre, producto_nombre, task_id)

            log_sync_action(
                proyecto_nombre=proyecto_nombre,
                odoo_model="project.task",
                accion="updated",
                odoo_id=task_id,
                producto_nombre=producto_nombre,
                detalle=f"Campos actualizados: {list(write_vals.keys())}",
            )
            return task_id, "updated"

        else:
            # Tarea no existe → crear
            task_id = client.create("project.task", vals)
            logger.info(
                f"    ✅ Tarea creada: '{producto_nombre}' "
                f"(Odoo ID: {task_id})"
            )

            # Guardar odoo_id en BD local
            save_producto_odoo_id(proyecto_nombre, producto_nombre, task_id)

            log_sync_action(
                proyecto_nombre=proyecto_nombre,
                odoo_model="project.task",
                accion="created",
                odoo_id=task_id,
                producto_nombre=producto_nombre,
                detalle=f"Creada con campos: {list(vals.keys())}",
            )
            return task_id, "created"

    except OdooClientError as e:
        logger.error(
            f"    ❌ Error sincronizando tarea '{producto_nombre}' "
            f"del proyecto '{proyecto_nombre}': {e}"
        )
        log_sync_action(
            proyecto_nombre=proyecto_nombre,
            odoo_model="project.task",
            accion="error",
            odoo_id=None,
            producto_nombre=producto_nombre,
            detalle=str(e),
        )
        return None, "error"
