"""Balanza de mostrador: configuracion del comercio y lectura de etiquetas.

El parser vive en `libracommerce.domain.scale` (es logica comercial, no de
VentaLibra). Aca esta lo que lo rodea: donde se guarda la configuracion del
local, y como se resuelve una etiqueta a un producto con su cantidad.
"""
import json
from dataclasses import asdict, dataclass
from decimal import Decimal

from libracommerce.domain.catalog import CatalogItem, ItemCodeType
from libracommerce.domain.scale import (
    ScaleFormat,
    ScaleValueKind,
    parse_scale_barcode,
)
from libracore.db.core import Conexion

from ..commerce import repositorio

#: Clave en `commerce_settings`. La balanza esta apagada mientras no exista.
SCALE_FORMAT_KEY = "scale.format"


class ScaleLabelError(Exception):
    """La etiqueta se leyo bien pero no se puede vender lo que dice."""


@dataclass(frozen=True)
class ScanResult:
    """Un escaneo ya resuelto: que producto es y cuanto se lleva.

    Para un codigo de barras comun la cantidad es 1 y el precio lo decide
    la lista de precios, como siempre. Lo que cambia con una etiqueta de
    balanza es que el codigo ya trae la cantidad (o el importe) adentro.
    """

    item: CatalogItem
    quantity: Decimal = Decimal("1")
    #: Solo cuando la balanza vino con el importe ya calculado. En ese caso
    #: se cobra este precio y no el de la lista, porque es el que esta
    #: impreso en la etiqueta pegada al producto.
    unit_price: Decimal | None = None
    from_scale: bool = False


class ScaleService:
    def __init__(self, conn: Conexion):
        self._conn = conn
        self._repo = repositorio(conn)

    def get_format(self) -> ScaleFormat | None:
        crudo = self._repo.get_setting(SCALE_FORMAT_KEY)
        if not crudo:
            return None
        datos = json.loads(crudo)
        datos["value_kind"] = ScaleValueKind(datos["value_kind"])
        return ScaleFormat(**datos)

    def set_format(self, fmt: ScaleFormat | None) -> None:
        """Guarda la configuracion, o la borra para apagar la balanza."""
        if fmt is None:
            self._conn.execute(
                "DELETE FROM commerce_settings WHERE key = ?", (SCALE_FORMAT_KEY,)
            )
            self._conn.commit()
            return
        datos = asdict(fmt)
        datos["value_kind"] = fmt.value_kind.value
        self._repo.set_setting(SCALE_FORMAT_KEY, json.dumps(datos))

    def scan(self, code: str) -> ScanResult | None:
        """Resuelve un codigo escaneado, sea de balanza o comun.

        Devuelve None si ningun producto corresponde al codigo; levanta
        `ScaleLabelError` cuando la etiqueta SI es de balanza pero apunta a
        algo que no se puede vender asi -- son dos problemas distintos y el
        cajero necesita distinguirlos.
        """
        fmt = self.get_format()
        leido = parse_scale_barcode(code, fmt) if fmt is not None else None

        if leido is None:
            item = self._repo.find_item_by_code(code)
            return None if item is None else ScanResult(item=item)

        item = self._repo.find_item_by_code(leido.item_code, code_type=ItemCodeType.SCALE)
        if item is None:
            raise ScaleLabelError(
                f"la etiqueta es del producto {leido.item_code} de la balanza, "
                "que no esta cargado en el catalogo"
            )

        if leido.kind is ScaleValueKind.WEIGHT:
            if not item.unit.allows_fraction:
                # Vender "0,750" de algo que se cuenta por unidad es un error
                # de carga (el codigo de balanza quedo en el producto
                # equivocado), y cobrarlo igual seria peor que frenar aca.
                raise ScaleLabelError(
                    f"{item.name} se vende por {item.unit.name.lower()} y no admite "
                    "fracciones, asi que no puede venir de la balanza por peso"
                )
            return ScanResult(item=item, quantity=leido.value, from_scale=True)

        return ScanResult(item=item, unit_price=leido.value, from_scale=True)
