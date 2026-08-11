# odoo_client.py — Cliente HTTP para la API JSON-2 de Odoo
"""
Encapsula todas las llamadas HTTP a la External JSON-2 API de Odoo 19.0.
Endpoint: POST /json/2/<model>/<method>
Auth: Bearer token + X-Odoo-Database header
"""

import os
import time
import logging
import requests
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

logger = logging.getLogger("odoo_sync")

# Cargar variables de entorno desde .env
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

ODOO_URL = os.getenv("ODOO_URL", "").rstrip("/")
ODOO_DATABASE = os.getenv("ODOO_DATABASE", "")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "")


class OdooClientError(Exception):
    """Error personalizado para fallos en la comunicación con Odoo."""
    pass


class OdooClient:
    """
    Cliente para la API JSON-2 de Odoo.
    
    Uso:
        client = OdooClient()
        projects = client.search_read("project.project", [["name", "=", "Mi Proyecto"]], ["id", "name"])
        new_id = client.create("project.project", {"name": "Nuevo Proyecto"})
        client.write("project.project", new_id, {"name": "Nombre Actualizado"})
    """

    def __init__(self, url: str = None, database: str = None, api_key: str = None, allow_unconfigured: bool = False):
        self.url = (url or ODOO_URL).rstrip("/")
        self.database = database or ODOO_DATABASE
        self.api_key = api_key or ODOO_API_KEY

        if not allow_unconfigured and (not self.url or not self.database or not self.api_key):
            raise OdooClientError(
                "Faltan credenciales de Odoo. Verificar el archivo .env "
                "(ODOO_URL, ODOO_DATABASE, ODOO_API_KEY)."
            )

        self._headers = {
            "Authorization": f"bearer {self.api_key}",
            "X-Odoo-Database": self.database,
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "OdooIntegration-SetIN/1.0",
        }

    # Reintentos ante fallos transitorios (red caída, timeout, 5xx del servidor).
    # Los 4xx (auth/validación/dominio inválido) son permanentes: no se reintentan.
    _MAX_RETRIES = 3
    _BACKOFF_BASE_SECONDS = 1.5  # 1.5s, 3s, 6s

    def _call(self, model: str, method: str, body: Dict = None) -> Any:
        """
        Realiza una petición POST a /json/2/<model>/<method>.
        Reintenta con backoff exponencial ante errores de red o HTTP 5xx
        (transitorios). Los HTTP 4xx y los errores devueltos en el cuerpo
        JSON se consideran permanentes y no se reintentan.
        Retorna el cuerpo JSON de la respuesta o lanza OdooClientError.
        """
        endpoint = f"{self.url}/json/2/{model}/{method}"
        last_error: Optional[Exception] = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                response = requests.post(
                    endpoint,
                    headers=self._headers,
                    json=body or {},
                    timeout=30,
                )
            except requests.RequestException as e:
                last_error = e
                if attempt < self._MAX_RETRIES:
                    wait = self._BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                    logger.warning(
                        f"Error de red llamando a Odoo ({model}/{method}), "
                        f"intento {attempt}/{self._MAX_RETRIES}: {e}. "
                        f"Reintentando en {wait:.1f}s..."
                    )
                    time.sleep(wait)
                    continue
                raise OdooClientError(f"Error de red al contactar Odoo: {e}")

            if response.status_code >= 500:
                last_error = OdooClientError(
                    f"Odoo respondió con HTTP {response.status_code}: {response.text[:500]}"
                )
                if attempt < self._MAX_RETRIES:
                    wait = self._BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                    logger.warning(
                        f"Odoo respondió {response.status_code} (transitorio) en "
                        f"{model}/{method}, intento {attempt}/{self._MAX_RETRIES}. "
                        f"Reintentando en {wait:.1f}s..."
                    )
                    time.sleep(wait)
                    continue
                raise last_error

            if response.status_code != 200:
                # 4xx u otro código no-5xx: error permanente, no se reintenta.
                raise OdooClientError(
                    f"Odoo respondió con HTTP {response.status_code}: {response.text[:500]}"
                )

            data = response.json()

            # La API JSON-2 puede devolver errores dentro de un JSON válido
            if isinstance(data, dict) and "error" in data:
                error_info = data["error"]
                msg = error_info.get("message", str(error_info))
                raise OdooClientError(f"Error de Odoo ({model}/{method}): {msg}")

            return data

        # No debería alcanzarse (el loop siempre retorna o lanza), pero por seguridad:
        raise OdooClientError(f"Fallo llamando a Odoo tras reintentos: {last_error}")

    # --- Métodos de alto nivel ---

    def search(self, model: str, domain: List, limit: int = 0) -> List[int]:
        """
        Busca registros que coincidan con el dominio y retorna sus IDs.
        """
        body = {"domain": domain}
        if limit:
            body["limit"] = limit
        result = self._call(model, "search", body)
        return result if isinstance(result, list) else []

    def search_read(
        self, model: str, domain: List, fields: List[str], limit: int = 0
    ) -> List[Dict]:
        """
        Busca registros y retorna los campos solicitados.
        """
        body = {
            "domain": domain,
            "fields": fields,
        }
        if limit:
            body["limit"] = limit
        result = self._call(model, "search_read", body)
        return result if isinstance(result, list) else []

    def create(self, model: str, vals: Dict) -> int:
        """
        Crea un registro nuevo en Odoo.
        Retorna el ID del registro creado.
        """
        body = {"vals_list": [vals]}
        result = self._call(model, "create", body)

        # La respuesta puede ser [id] o [{"id": id}]
        if isinstance(result, list) and len(result) > 0:
            item = result[0]
            if isinstance(item, dict):
                return item.get("id", item)
            return item

        raise OdooClientError(
            f"Respuesta inesperada al crear {model}: {result}"
        )

    def write(self, model: str, record_id: int, vals: Dict) -> bool:
        """
        Actualiza un registro existente en Odoo.
        Retorna True si la operación fue exitosa.
        """
        body = {"ids": [record_id], "vals": vals}
        result = self._call(model, "write", body)
        return bool(result)

    def test_connection(self) -> bool:
        """
        Verifica la conectividad haciendo un search_read mínimo.
        Retorna True si la conexión es exitosa.
        """
        try:
            self.search_read("res.company", [], ["name"], limit=1)
            return True
        except OdooClientError:
            return False
