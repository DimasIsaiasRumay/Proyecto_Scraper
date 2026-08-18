# test_odoo_locations.py — Pruebas unitarias para sync_locations.py
"""
Pruebas de saneo de nombres, armado de payloads, resolución de ProductionParent
y lógica de sincronización individual (sync_one_location).
No realiza llamadas de red; utiliza un FakeClient local.
"""

import pytest
from typing import Any, Dict, List, Optional, Tuple

from odoo_client import OdooClientError
from odoo_models import ProyectoLocal
import sync_locations
from sync_locations import (
    ProductionParent,
    build_location_vals,
    resolve_production_location,
    sanitize_location_name,
    sync_one_location,
)


def _domain_matches(expected_domain: Any, actual_domain: list) -> bool:
    """Verifica si actual_domain coincide con expected_domain."""
    if expected_domain is None:
        return True
    if expected_domain == actual_domain:
        return True
    # Comparar como listas de tuplas
    def norm(d):
        return [tuple(elem) if isinstance(elem, list) else elem for elem in d]
    return norm(expected_domain) == norm(actual_domain)


class FakeClient:
    """Cliente simulado de Odoo en memoria para pruebas unitarias."""

    def __init__(
        self,
        respuestas: Optional[List[Tuple[Tuple[str, Any], list]]] = None,
        create_id: int = 999,
        fallar: bool = False,
    ):
        self.reglas: List[Tuple[str, Any, list]] = []
        if respuestas:
            for item in respuestas:
                if isinstance(item, tuple) and len(item) == 2:
                    (m, dom), res = item
                    self.reglas.append((m, dom, res))
        self.create_id = create_id
        self.fallar = fallar
        self.consultas: List[Tuple[str, list]] = []
        self.creados: List[Dict] = []

    def search_read(
        self, model: str, domain: list, fields: list, limit: int = 0
    ) -> list:
        self.consultas.append((model, domain))
        if self.fallar:
            raise OdooClientError("Error simulado de comunicación con Odoo")

        for m, dom, res in self.reglas:
            if m == model and _domain_matches(dom, domain):
                return res
        return []

    def create(self, model: str, vals: dict) -> int:
        if self.fallar:
            raise OdooClientError("Error simulado al crear en Odoo")
        self.creados.append(vals)
        return self.create_id

    def _call(self, model: str, method: str, body: Any = None):
        raise AssertionError(f"_call no debería invocarse en estas pruebas: {model}.{method}")


# --- 1. Saneo de nombres ---

class TestSanitizeLocationName:
    def test_nombre_real_con_barra(self):
        entrada = "OP_ITC_Caja p/Baterias_1504261521"
        esperado = "OP_ITC_Caja p-Baterias_1504261521"
        assert sanitize_location_name(entrada) == esperado

    def test_multiples_barras(self):
        assert sanitize_location_name("a/b/c") == "a-b-c"

    def test_recorta_espacios_de_los_bordes(self):
        assert sanitize_location_name("  OP_X  ") == "OP_X"

    def test_nombre_sin_barra_queda_igual(self):
        nombre = "OP-CTOM-GAB-120826-0002"
        assert sanitize_location_name(nombre) == nombre

    def test_conserva_comillas_parentesis_y_punto(self):
        casos = [
            'OP_TOTEM_INC32"_2605260826',
            "OP_TELECOM_MORSETOS26 (2)_1603260739",
            "OP_VIALTRUCK_VOLCADORA9.3_2005260959",
        ]
        for caso in casos:
            assert sanitize_location_name(caso) == caso


# --- 2. Armado de payload (build_location_vals) ---

class TestBuildLocationVals:
    def test_campos_exactos(self):
        vals = build_location_vals("OP_TEST", 12, 1)
        assert vals == {
            "name": "OP_TEST",
            "location_id": 12,
            "usage": "production",
            "company_id": 1,
        }

    def test_sin_company_id_no_incluye_la_clave(self):
        vals = build_location_vals("OP_TEST", 12, None)
        assert "company_id" not in vals
        assert vals == {
            "name": "OP_TEST",
            "location_id": 12,
            "usage": "production",
        }

    def test_nunca_escribe_complete_name(self):
        vals = build_location_vals("OP_TEST", 12, 1)
        assert "complete_name" not in vals


# --- 3. Resolución de ubicación padre 'Production' ---

class TestResolveProductionLocation:
    def test_usa_xmlid_cuando_existe(self):
        respuestas = [
            (
                ("ir.model.data", [["module", "=", "stock"], ["name", "=", "location_production"]]),
                [{"res_id": 12}],
            ),
            (
                ("stock.location", [["id", "=", 12]]),
                [
                    {
                        "id": 12,
                        "name": "Production",
                        "complete_name": "Production",
                        "usage": "production",
                        "location_id": False,
                        "company_id": [1, "SET IN SAS"],
                        "active": True,
                    }
                ],
            ),
        ]
        client = FakeClient(respuestas=respuestas)
        parent = resolve_production_location(client)
        assert parent is not None
        assert parent.id == 12
        assert parent.company_id == 1
        assert any(c[0] == "ir.model.data" for c in client.consultas)

    def test_fallback_por_nombre_cuando_no_hay_xmlid(self):
        respuestas = [
            (
                ("stock.location", [["usage", "=", "production"], ["location_id", "=", False], ["active", "=", True]]),
                [
                    {
                        "id": 12,
                        "name": "Production",
                        "complete_name": "Production",
                        "usage": "production",
                        "location_id": False,
                        "company_id": [1, "SET IN SAS"],
                        "active": True,
                    }
                ],
            )
        ]
        client = FakeClient(respuestas=respuestas)
        parent = resolve_production_location(client)
        assert parent is not None
        assert parent.id == 12
        assert parent.company_id == 1

    def test_rechaza_sub_ubicacion_propia(self):
        respuestas = [
            (
                ("stock.location", [["usage", "=", "production"], ["location_id", "=", False], ["active", "=", True]]),
                [
                    {
                        "id": 16,
                        "name": "OP-SUB",
                        "complete_name": "Production/OP-SUB",
                        "usage": "production",
                        "location_id": [12, "Production"],
                        "company_id": [1, "SET IN SAS"],
                        "active": True,
                    }
                ],
            )
        ]
        client = FakeClient(respuestas=respuestas)
        parent = resolve_production_location(client)
        assert parent is None

    def test_ambiguo_devuelve_none(self):
        respuestas = [
            (
                ("stock.location", [["usage", "=", "production"], ["location_id", "=", False], ["active", "=", True]]),
                [
                    {"id": 12, "name": "Prod1", "complete_name": "Prod1", "usage": "production", "location_id": False, "active": True},
                    {"id": 13, "name": "Prod2", "complete_name": "Prod2", "usage": "production", "location_id": False, "active": True},
                ],
            )
        ]
        client = FakeClient(respuestas=respuestas)
        parent = resolve_production_location(client)
        assert parent is None

    def test_normaliza_company_id(self):
        # Caso 1: [1, 'SET IN SAS'] -> 1
        r1 = [
            (
                ("stock.location", [["usage", "=", "production"], ["location_id", "=", False], ["active", "=", True]]),
                [
                    {
                        "id": 12,
                        "name": "Production",
                        "complete_name": "Production",
                        "usage": "production",
                        "location_id": False,
                        "company_id": [1, "SET IN SAS"],
                        "active": True,
                    }
                ],
            )
        ]
        p1 = resolve_production_location(FakeClient(respuestas=r1))
        assert p1 is not None and p1.company_id == 1

        # Caso 2: False -> None
        r2 = [
            (
                ("stock.location", [["usage", "=", "production"], ["location_id", "=", False], ["active", "=", True]]),
                [
                    {
                        "id": 12,
                        "name": "Production",
                        "complete_name": "Production",
                        "usage": "production",
                        "location_id": False,
                        "company_id": False,
                        "active": True,
                    }
                ],
            )
        ]
        p2 = resolve_production_location(FakeClient(respuestas=r2))
        assert p2 is not None and p2.company_id is None


# --- 4. Sincronización individual (sync_one_location) ---

@pytest.fixture(autouse=True)
def mock_db_writes(monkeypatch):
    """Evita escrituras en la base de datos real durante los tests."""
    monkeypatch.setattr(sync_locations, "save_project_location_id", lambda *a, **k: None)
    monkeypatch.setattr(sync_locations, "log_sync_action", lambda *a, **k: None)


class TestSyncOneLocation:
    def test_crea_cuando_no_existe(self):
        proyecto = ProyectoLocal(nombre="OP-NUEVO")
        parent = ProductionParent(id=12, company_id=1)
        client = FakeClient(create_id=555)

        loc_id, accion = sync_one_location(client, proyecto, parent, dry_run=False)
        assert accion == "created"
        assert loc_id == 555
        assert len(client.creados) == 1
        assert client.creados[0] == {
            "name": "OP-NUEVO",
            "location_id": 12,
            "usage": "production",
            "company_id": 1,
        }

    def test_busca_con_el_nombre_saneado(self):
        """Regresión del duplicado: la búsqueda debe usar el nombre ya saneado."""
        proyecto = ProyectoLocal(nombre="OP_ITC_Caja p/Baterias_1504261521")
        parent = ProductionParent(id=12, company_id=1)
        client = FakeClient(create_id=777)

        sync_one_location(client, proyecto, parent, dry_run=False)
        searched_domains = [c[1] for c in client.consultas]
        assert any(["name", "=", "OP_ITC_Caja p-Baterias_1504261521"] in d for d in searched_domains)
        assert not any(["name", "=", "OP_ITC_Caja p/Baterias_1504261521"] in d for d in searched_domains)

    def test_sin_cambios_cuando_ya_existe_igual(self):
        proyecto = ProyectoLocal(nombre="OP-EXISTE", odoo_location_id=16)
        parent = ProductionParent(id=12, company_id=1)
        respuestas = [
            (
                ("stock.location", [["name", "=", "OP-EXISTE"], ["location_id", "=", 12], ["active", "in", [True, False]]]),
                [
                    {
                        "id": 16,
                        "name": "OP-EXISTE",
                        "complete_name": "Production/OP-EXISTE",
                        "usage": "production",
                        "location_id": [12, "Production"],
                        "active": True,
                    }
                ],
            )
        ]
        client = FakeClient(respuestas=respuestas)
        loc_id, accion = sync_one_location(client, proyecto, parent, dry_run=False)
        assert accion == "sin_cambios"
        assert loc_id == 16
        assert client.creados == []

    def test_aviso_si_usage_distinto(self):
        proyecto = ProyectoLocal(nombre="OP-OTRO-TIPO")
        parent = ProductionParent(id=12, company_id=1)
        respuestas = [
            (
                ("stock.location", [["name", "=", "OP-OTRO-TIPO"], ["location_id", "=", 12], ["active", "in", [True, False]]]),
                [
                    {
                        "id": 20,
                        "name": "OP-OTRO-TIPO",
                        "complete_name": "Production/OP-OTRO-TIPO",
                        "usage": "internal",
                        "location_id": [12, "Production"],
                        "active": True,
                    }
                ],
            )
        ]
        client = FakeClient(respuestas=respuestas)
        loc_id, accion = sync_one_location(client, proyecto, parent, dry_run=False)
        assert accion == "aviso"
        assert loc_id == 20
        assert client.creados == []

    def test_aviso_si_esta_archivada(self):
        proyecto = ProyectoLocal(nombre="OP-ARCHIVADA")
        parent = ProductionParent(id=12, company_id=1)
        respuestas = [
            (
                ("stock.location", [["name", "=", "OP-ARCHIVADA"], ["location_id", "=", 12], ["active", "in", [True, False]]]),
                [
                    {
                        "id": 21,
                        "name": "OP-ARCHIVADA",
                        "complete_name": "Production/OP-ARCHIVADA",
                        "usage": "production",
                        "location_id": [12, "Production"],
                        "active": False,
                    }
                ],
            )
        ]
        client = FakeClient(respuestas=respuestas)
        loc_id, accion = sync_one_location(client, proyecto, parent, dry_run=False)
        assert accion == "aviso"
        assert loc_id == 21
        assert client.creados == []

    def test_aviso_si_hay_duplicados_bajo_el_padre(self):
        proyecto = ProyectoLocal(nombre="OP-DUPLICADA")
        parent = ProductionParent(id=12, company_id=1)
        respuestas = [
            (
                ("stock.location", [["name", "=", "OP-DUPLICADA"], ["location_id", "=", 12], ["active", "in", [True, False]]]),
                [
                    {"id": 30, "name": "OP-DUPLICADA", "usage": "production", "active": True},
                    {"id": 31, "name": "OP-DUPLICADA", "usage": "production", "active": True},
                ],
            )
        ]
        client = FakeClient(respuestas=respuestas)
        loc_id, accion = sync_one_location(client, proyecto, parent, dry_run=False)
        assert accion == "aviso"
        assert loc_id is None
        assert client.creados == []

    def test_aviso_si_existe_fuera_de_production(self):
        proyecto = ProyectoLocal(nombre="OP-FUERA")
        parent = ProductionParent(id=12, company_id=1)
        respuestas = [
            # Bajo Production -> vacio
            (
                ("stock.location", [["name", "=", "OP-FUERA"], ["location_id", "=", 12], ["active", "in", [True, False]]]),
                [],
            ),
            # Global -> existe en WH
            (
                ("stock.location", [["name", "=", "OP-FUERA"], ["active", "in", [True, False]]]),
                [
                    {
                        "id": 40,
                        "name": "OP-FUERA",
                        "complete_name": "WH/OP-FUERA",
                        "location_id": [4, "WH"],
                        "usage": "internal",
                        "active": True,
                    }
                ],
            ),
        ]
        client = FakeClient(respuestas=respuestas)
        loc_id, accion = sync_one_location(client, proyecto, parent, dry_run=False)
        assert accion == "aviso"
        assert loc_id is None
        assert client.creados == []

    def test_dry_run_no_llama_create_ni_guarda(self, monkeypatch):
        guardados = []
        monkeypatch.setattr(
            sync_locations,
            "save_project_location_id",
            lambda nombre, lid: guardados.append((nombre, lid)),
        )
        proyecto = ProyectoLocal(nombre="OP-DRY")
        parent = ProductionParent(id=12, company_id=1)
        client = FakeClient(create_id=888)

        loc_id, accion = sync_one_location(client, proyecto, parent, dry_run=True)
        assert accion == "created"
        assert loc_id is None
        assert client.creados == []
        assert guardados == []

    def test_error_de_odoo_devuelve_error(self):
        proyecto = ProyectoLocal(nombre="OP-ERROR")
        parent = ProductionParent(id=12, company_id=1)
        client = FakeClient(fallar=True)

        loc_id, accion = sync_one_location(client, proyecto, parent, dry_run=False)
        assert accion == "error"
        assert loc_id is None
