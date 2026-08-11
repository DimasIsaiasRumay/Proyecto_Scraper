# config.py — Configuración y credenciales del scraper
import os
from dotenv import load_dotenv

# Directorio base del script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Cargar credenciales desde .env (mismo mecanismo que odoo-integration/, para
# no tener dos formatos distintos de manejo de secretos en el mismo proyecto).
load_dotenv(os.path.join(BASE_DIR, ".env"))


class ConfigError(Exception):
    """Error de configuración: falta el archivo .env o está incompleto."""
    pass


BASE_URL = os.getenv("SET_IN_URL", "").strip()
USERNAME = os.getenv("SET_IN_USERNAME", "").strip()
PASSWORD = os.getenv("SET_IN_PASSWORD", "").strip()

# Antes había un usuario y contraseña de respaldo hardcodeados acá, que se
# usaban en silencio si el archivo de credenciales faltaba o no se pudo leer.
# Eso es un riesgo de seguridad (una cuenta real quedaba embebida en el código
# fuente) y además ocultaba el problema real al operador. Ahora, si falta el
# .env o está incompleto, se falla explícitamente en el arranque.
if not BASE_URL or not USERNAME or not PASSWORD:
    raise ConfigError(
        f"No se pudieron leer las credenciales completas desde "
        f"{os.path.join(BASE_DIR, '.env')!r}. Verificá que el archivo exista "
        f"y tenga SET_IN_URL, SET_IN_USERNAME y SET_IN_PASSWORD completos "
        f"(ver .env.example en esta misma carpeta como referencia de formato)."
    )

# Normalizar URL
if BASE_URL.endswith("/"):
    BASE_URL = BASE_URL[:-1]

# Páginas
URL_LOGIN = f"{BASE_URL}/"
URL_PROYECTOS = f"{BASE_URL}/proyecto_master_v16.html"
URL_MATERIALES = f"{BASE_URL}/proyecto_master_material_logistica_v18.html"

# Playwright
HEADLESS = True
TIMEOUT_NAV = 45_000          # ms — espera de navegación (aumentada para robustez)
TIMEOUT_ELEMENT = 20_000      # ms — espera de elementos

# Rango de pausas aleatorias para simular interacción humana (en segundos)
DELAY_MIN = 1.5
DELAY_MAX = 3.5

# Ventanas horarias permitidas para ejecución automática (Local Time)
TIME_WINDOWS = [
    ("06:11", "07:22"),
    ("16:00", "17:00")
]

# Rutas de persistencia y archivos del sistema
DB_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DB_DIR, "fabricacion.db")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "scraper.log")
LOCK_PATH = os.path.join(BASE_DIR, "scraper.lock")

# Logging rotativo
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 3
