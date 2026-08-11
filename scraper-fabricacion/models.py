import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("scraper")

# Valores válidos conocidos para campos "tipo"/"estado" que hoy son strings
# libres. No se usa un Enum estricto porque el ERP puede introducir estados
# nuevos que no rompan el scraping (se loguean como advertencia en vez de
# fallar), pero sirve para detectar valores inesperados (typos de scraping,
# columnas desplazadas) sin necesidad de leer el log línea por línea.
TIPOS_MATERIAL_CONOCIDOS = {"item", "suministro"}


def _validar_opcional_float(valor, campo: str, contexto: str) -> None:
    if valor is not None and not isinstance(valor, (int, float)):
        logger.warning(
            f"{contexto}: campo '{campo}' esperaba float/None y llegó "
            f"{type(valor).__name__}={valor!r}."
        )


def _validar_opcional_str(valor, campo: str, contexto: str) -> None:
    if valor is not None and not isinstance(valor, str):
        logger.warning(
            f"{contexto}: campo '{campo}' esperaba str/None y llegó "
            f"{type(valor).__name__}={valor!r}."
        )


@dataclass
class ProductoItem:
    nombre: str
    cantidad: Optional[float]
    solicitud: Optional[str]       # fecha string "YYYY-MM-DD"
    entrega_fc: Optional[str]
    entrega: Optional[str]
    estado: str

    def __post_init__(self):
        if not self.nombre or not self.nombre.strip():
            logger.warning("ProductoItem con 'nombre' vacío o ausente; revisar fila de origen en el DOM.")
        _validar_opcional_float(self.cantidad, "cantidad", f"ProductoItem({self.nombre!r})")


@dataclass
class Producto:
    proyecto_nombre: str
    nombre: str
    cantidad: Optional[float]
    solicitud: Optional[str]       # fecha string "YYYY-MM-DD"
    entrega_fc: Optional[str]
    entrega: Optional[str]
    estado: str
    items: List[ProductoItem] = field(default_factory=list)

    def __post_init__(self):
        if not self.nombre or not self.nombre.strip():
            logger.warning(f"Producto sin 'nombre' en proyecto '{self.proyecto_nombre}'; revisar fila de origen en el DOM.")
        _validar_opcional_float(self.cantidad, "cantidad", f"Producto({self.nombre!r})")


@dataclass
class Proyecto:
    nombre: str
    cliente: str
    estado: str
    productos: List[Producto] = field(default_factory=list)

    def __post_init__(self):
        if not self.nombre or self.nombre == "N/A":
            logger.warning("Proyecto con 'nombre' vacío o no reconocido ('N/A'); posible cambio de estructura en la tabla de proyectos del ERP.")


@dataclass
class Material:
    proyecto_nombre: str
    tipo: str                      # "item" | "suministro"
    codigo_mp: str
    descripcion: str
    proveedor: Optional[str]
    cantidad: Optional[float]
    desperdicio_12: Optional[float]
    validacion_diseno: Optional[float]
    stock_chapa_barras: Optional[float]
    comprar: Optional[float]
    precio_sw: Optional[float]
    precio_compra: Optional[float]
    orden_compra: Optional[str]
    numero_factura: Optional[str]
    estado_compra: str
    comentarios: Optional[str]

    def __post_init__(self):
        if self.tipo not in TIPOS_MATERIAL_CONOCIDOS:
            logger.warning(
                f"Material con 'tipo' desconocido: {self.tipo!r} (esperado uno de "
                f"{TIPOS_MATERIAL_CONOCIDOS}) en proyecto '{self.proyecto_nombre}', "
                f"código '{self.codigo_mp}'. Puede indicar un cambio en el ERP."
            )
        for campo, valor in (
            ("cantidad", self.cantidad),
            ("desperdicio_12", self.desperdicio_12),
            ("validacion_diseno", self.validacion_diseno),
            ("stock_chapa_barras", self.stock_chapa_barras),
            ("comprar", self.comprar),
            ("precio_sw", self.precio_sw),
            ("precio_compra", self.precio_compra),
        ):
            _validar_opcional_float(valor, campo, f"Material({self.codigo_mp!r}, {self.proyecto_nombre!r})")
