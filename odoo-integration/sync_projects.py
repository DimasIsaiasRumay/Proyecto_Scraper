# sync_projects.py — Sincronización de proyectos con Odoo (project.project)
"""
Lógica de upsert para el modelo project.project de Odoo.
Estrategia de búsqueda:
  1. Si el proyecto tiene odoo_id guardado en la BD local → buscar por ID (rápido)
  2. Si no → buscar por nombre exacto (fallback)
Si existe → write, si no → create.
Tras crear/actualizar, guarda el odoo_id en la BD local.
"""

import logging
from typing import Dict, Optional, Tuple

from odoo_client import OdooClient, OdooClientError
from sync_logger import log_sync_action
from database_reader import save_project_odoo_id
from odoo_models import ProyectoLocal

logger = logging.getLogger("odoo_sync")

# Campos que se leen de Odoo para verificar existencia
_SEARCH_FIELDS = ["id", "name", "description"]


def _build_odoo_vals(project: ProyectoLocal) -> Dict:
    """
    Construye el diccionario de valores para crear/actualizar en Odoo.
    Mapea los campos de ProyectoLocal a los campos de project.project.
    (El acceso es por atributo, no por clave de dict: un typo acá lo marca
    el propio Python/IDE al momento, en vez de fallar recién en producción).
    """
    # Construir descripción combinando cliente y estado
    description_parts = []
    if project.cliente:
        description_parts.append(f"Cliente: {project.cliente}")
    if project.estado:
        description_parts.append(f"Estado: {project.estado}")

    vals = {
        "name": project.nombre,
    }

    if description_parts:
        vals["description"] = " | ".join(description_parts)

    return vals


def sync_one_project(
    client: OdooClient, project: ProyectoLocal, dry_run: bool = False
) -> Tuple[Optional[int], str]:
    """
    Sincroniza un proyecto individual con Odoo.

    Parámetros:
        client: Instancia de OdooClient.
        project: ProyectoLocal (nombre, cliente, estado, odoo_id, productos).
        dry_run: Si True, no hace cambios en Odoo.

    Retorna:
        (odoo_id, accion) donde accion es 'created', 'updated', 'skipped', o 'error'.
    """
    nombre = project.nombre
    local_odoo_id = project.odoo_id
    vals = _build_odoo_vals(project)

    # En modo dry-run, no hacer ninguna llamada a Odoo
    if dry_run:
        if local_odoo_id:
            logger.info(f"  [DRY-RUN] Actualizaría proyecto '{nombre}' (Odoo ID local: {local_odoo_id})")
        else:
            logger.info(f"  [DRY-RUN] Sincronizaría proyecto '{nombre}' → campos: {list(vals.keys())}")
        return local_odoo_id, "skipped"

    try:
        existing = None

        # 1. Si tenemos odoo_id guardado, verificar que siga existiendo en Odoo
        if local_odoo_id:
            try:
                check = client.search_read(
                    "project.project",
                    [["id", "=", local_odoo_id]],
                    ["id"],
                    limit=1,
                )
                if check:
                    existing = check
            except OdooClientError:
                # Si falla, caemos al fallback por nombre
                pass

        # 2. Fallback: buscar por nombre exacto
        if not existing:
            existing = client.search_read(
                "project.project",
                [["name", "=", nombre]],
                _SEARCH_FIELDS,
                limit=1,
            )

        if existing:
            # Proyecto ya existe → actualizar
            odoo_id = existing[0]["id"]
            client.write("project.project", odoo_id, vals)
            logger.info(f"  ✏️  Proyecto actualizado: '{nombre}' (Odoo ID: {odoo_id})")

            # Guardar odoo_id en BD local (por si era un fallback por nombre)
            save_project_odoo_id(nombre, odoo_id)

            log_sync_action(
                proyecto_nombre=nombre,
                odoo_model="project.project",
                accion="updated",
                odoo_id=odoo_id,
                detalle=f"Campos actualizados: {list(vals.keys())}",
            )
            return odoo_id, "updated"

        else:
            # Proyecto no existe → crear
            odoo_id = client.create("project.project", vals)
            logger.info(f"  ✅ Proyecto creado: '{nombre}' (Odoo ID: {odoo_id})")

            # Guardar odoo_id en BD local
            save_project_odoo_id(nombre, odoo_id)

            log_sync_action(
                proyecto_nombre=nombre,
                odoo_model="project.project",
                accion="created",
                odoo_id=odoo_id,
                detalle=f"Creado con campos: {list(vals.keys())}",
            )
            return odoo_id, "created"

    except OdooClientError as e:
        logger.error(f"  ❌ Error sincronizando proyecto '{nombre}': {e}")
        log_sync_action(
            proyecto_nombre=nombre,
            odoo_model="project.project",
            accion="error",
            detalle=str(e),
        )
        return None, "error"


def get_project_odoo_id(client: OdooClient, nombre: str) -> Optional[int]:
    """
    Obtiene el ID de Odoo de un proyecto buscando por nombre.
    Útil para asociar tareas (productos) al proyecto correcto.
    """
    try:
        existing = client.search_read(
            "project.project",
            [["name", "=", nombre]],
            ["id"],
            limit=1,
        )
        if existing:
            return existing[0]["id"]
    except OdooClientError as e:
        logger.error(f"Error buscando proyecto '{nombre}' en Odoo: {e}")
    return None
