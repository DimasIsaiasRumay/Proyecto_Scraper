# sync_locations.py — Creación de ubicaciones de producción en Odoo (stock.location)
"""
Lógica para crear y verificar ubicaciones virtuales de producción en Odoo 19.0.
Cada proyecto del bot se mapea como una sub-ubicación de 'Production'
(stock.location con usage='production' y location_id apuntando al padre).

Estrategia de búsqueda y resolución:
  1. Resolver ubicación padre 'Production' (por XML ID o fallback por nombre/usage).
  2. Para cada proyecto, buscar primero bajo el padre Production.
  3. Si no existe bajo el padre, buscar globalmente para evitar duplicar nombres
     que existan en otras ramas del árbol.
  4. Si no existe en ningún lado → create bajo Production.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from odoo_client import OdooClient, OdooClientError
from sync_logger import log_sync_action
from database_reader import save_project_location_id
from odoo_models import ProyectoLocal

logger = logging.getLogger("odoo_sync")

_MODEL = "stock.location"
_SEARCH_FIELDS = ["id", "name", "complete_name", "usage", "location_id", "active"]
_XMLID_CANDIDATES = (("stock", "location_production"), ("stock", "stock_location_production"))
_USAGE = "production"


@dataclass
class ProductionParent:
    """Representa la ubicación padre 'Production' resuelta en Odoo."""
    id: int
    company_id: Optional[int] = None


def sanitize_location_name(nombre: str) -> str:
    """
    Nombre apto para stock.location: '/' es separador de jerarquía en Odoo.
    Aplica:
      1. nombre.strip()
      2. Reemplazar '/' por '-'
    """
    return nombre.strip().replace("/", "-")


def _is_valid_production_parent(loc: Dict) -> bool:
    """Valida que el candidato sea la ubicación padre 'Production' y no una sub-ubicación."""
    if loc.get("usage") != _USAGE:
        return False
    if not loc.get("active"):
        return False
    parent_loc = loc.get("location_id")
    if parent_loc and isinstance(parent_loc, (list, tuple)) and len(parent_loc) >= 2:
        if parent_loc[1] == "Production":
            return False
    return True


def _build_production_parent(loc: Dict) -> ProductionParent:
    """Construye ProductionParent normalizando company_id."""
    company_raw = loc.get("company_id")
    company_id = None
    if isinstance(company_raw, (list, tuple)) and len(company_raw) > 0:
        company_id = company_raw[0]
    elif isinstance(company_raw, int) and company_raw > 0:
        company_id = company_raw
    return ProductionParent(id=loc["id"], company_id=company_id)


def resolve_production_location(client: OdooClient) -> Optional[ProductionParent]:
    """
    Resuelve la ubicación padre 'Production'. Se llama UNA vez por corrida.
    Retorna ProductionParent o None si no se puede resolver (abortar sincronización).
    """
    # 1. Por XML ID
    for mod, name in _XMLID_CANDIDATES:
        try:
            records = client.search_read(
                "ir.model.data",
                [["module", "=", mod], ["name", "=", name]],
                ["res_id"],
                limit=1,
            )
            if records and records[0].get("res_id"):
                res_id = records[0]["res_id"]
                locs = client.search_read(
                    _MODEL,
                    [["id", "=", res_id]],
                    _SEARCH_FIELDS + ["company_id"],
                    limit=1,
                )
                if locs and _is_valid_production_parent(locs[0]):
                    parent = _build_production_parent(locs[0])
                    logger.info(
                        f"🏭 Ubicación padre: 'Production' (Odoo ID: {parent.id}, empresa: {parent.company_id})"
                    )
                    return parent
        except OdooClientError:
            pass

    # 2. Fallback por nombre / usage
    try:
        candidates = client.search_read(
            _MODEL,
            [["usage", "=", _USAGE], ["location_id", "=", False], ["active", "=", True]],
            _SEARCH_FIELDS + ["company_id"],
            limit=5,
        )
        if len(candidates) == 0:
            candidates = client.search_read(
                _MODEL,
                [["name", "=", "Production"], ["location_id", "=", False], ["active", "=", True]],
                _SEARCH_FIELDS + ["company_id"],
                limit=5,
            )

        if len(candidates) == 1:
            if _is_valid_production_parent(candidates[0]):
                parent = _build_production_parent(candidates[0])
                logger.info(
                    f"🏭 Ubicación padre: 'Production' (Odoo ID: {parent.id}, empresa: {parent.company_id})"
                )
                return parent
            else:
                logger.error(
                    f"❌ El candidato encontrado para Production no es válido: {candidates[0]}"
                )
                return None
        elif len(candidates) > 1:
            desc = ", ".join([f"ID {c.get('id')} ({c.get('complete_name')})" for c in candidates])
            logger.error(
                f"❌ Múltiples candidatos ambiguos para Production: {desc}. Abortando."
            )
            return None
        else:
            logger.error("❌ No se encontró la ubicación padre 'Production' en Odoo.")
            return None
    except OdooClientError as e:
        logger.error(f"❌ Error al consultar ubicación padre en Odoo: {e}")
        return None


def build_location_vals(
    nombre_saneado: str, production_id: int, company_id: Optional[int] = None
) -> Dict:
    """Construye el diccionario de valores para crear stock.location en Odoo."""
    vals = {
        "name": nombre_saneado,
        "location_id": production_id,
        "usage": _USAGE,
    }
    if company_id:
        vals["company_id"] = company_id
    return vals


def sync_one_location(
    client: OdooClient,
    proyecto: ProyectoLocal,
    parent: ProductionParent,
    dry_run: bool = False,
) -> Tuple[Optional[int], str]:
    """
    Sincroniza una ubicación de producción individual con Odoo.

    Retorna:
        (odoo_location_id, accion) donde accion ∈ {'created', 'sin_cambios', 'aviso', 'error'}.
    """
    nombre = sanitize_location_name(proyecto.nombre)
    if not nombre:
        logger.warning(f"  ⚠️  Aviso en '{proyecto.nombre}': nombre vacío tras saneo")
        return (None, "aviso")

    # 1. Búsqueda bajo el padre Production
    try:
        existing = client.search_read(
            _MODEL,
            [["name", "=", nombre], ["location_id", "=", parent.id], ["active", "in", [True, False]]],
            _SEARCH_FIELDS,
            limit=2,
        )
    except OdooClientError as e:
        logger.error(f"  ❌ Error creando ubicación '{nombre}': {e}")
        log_sync_action(
            proyecto_nombre=proyecto.nombre,
            odoo_model=_MODEL,
            accion="error",
            odoo_id=None,
            detalle=str(e),
        )
        return (None, "error")

    if len(existing) >= 2:
        logger.warning(
            f"  ⚠️  Aviso en '{nombre}': existen múltiples ubicaciones duplicadas bajo Production en Odoo"
        )
        return (None, "aviso")

    if len(existing) == 1:
        loc = existing[0]
        loc_id = loc["id"]
        if not loc.get("active"):
            logger.warning(f"  ⚠️  Aviso en '{nombre}': la ubicación existe pero está archivada en Odoo")
            accion = "aviso"
        elif loc.get("usage") != _USAGE:
            logger.warning(
                f"  ⚠️  Aviso en '{nombre}': la ubicación existe con tipo '{loc.get('usage')}' en vez de '{_USAGE}'"
            )
            accion = "aviso"
        else:
            logger.info(f"  ➖ Ubicación ya existía: '{nombre}' (Odoo ID: {loc_id})")
            accion = "sin_cambios"

        if proyecto.odoo_location_id != loc_id and not dry_run:
            save_project_location_id(proyecto.nombre, loc_id)
        return (loc_id, accion)

    # 2. Búsqueda global (fuera de Production) para evitar duplicados en otras ramas
    try:
        global_match = client.search_read(
            _MODEL,
            [["name", "=", nombre], ["active", "in", [True, False]]],
            _SEARCH_FIELDS,
            limit=2,
        )
    except OdooClientError as e:
        logger.error(f"  ❌ Error creando ubicación '{nombre}': {e}")
        log_sync_action(
            proyecto_nombre=proyecto.nombre,
            odoo_model=_MODEL,
            accion="error",
            odoo_id=None,
            detalle=str(e),
        )
        return (None, "error")

    if global_match:
        complete_name = global_match[0].get("complete_name", global_match[0].get("name", nombre))
        logger.warning(
            f"  ⚠️  Aviso en '{nombre}': la ubicación ya existe fuera de Production ('{complete_name}')"
        )
        return (None, "aviso")

    # 3. Crear ubicación
    if dry_run:
        logger.info(f"  🆕 [DRY-RUN] Crearía ubicación: '{nombre}' bajo Production (ID {parent.id})")
        return (None, "created")

    try:
        vals = build_location_vals(nombre, parent.id, parent.company_id)
        nuevo_id = client.create(_MODEL, vals)
        save_project_location_id(proyecto.nombre, nuevo_id)
        log_sync_action(
            proyecto_nombre=proyecto.nombre,
            odoo_model=_MODEL,
            accion="created",
            odoo_id=nuevo_id,
            detalle=f"Creada bajo Production (ID {parent.id}) con nombre '{nombre}'",
        )
        logger.info(f"  ✅ Ubicación creada: '{nombre}' (Odoo ID: {nuevo_id})")
        return (nuevo_id, "created")
    except OdooClientError as e:
        logger.error(f"  ❌ Error creando ubicación '{nombre}': {e}")
        log_sync_action(
            proyecto_nombre=proyecto.nombre,
            odoo_model=_MODEL,
            accion="error",
            odoo_id=None,
            detalle=str(e),
        )
        return (None, "error")
