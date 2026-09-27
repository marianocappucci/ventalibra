"""Balanza de mostrador: la configuracion del comercio.

El parser vive en `libracommerce.domain.scale` y el escaneo (resolver una etiqueta a un producto con su cantidad) es
`GET /api/productos/escanear` del motor (fase 7, ADR-034). Acá queda dónde se guarda la configuración del local.
"""
import json
from dataclasses import asdict

from libracommerce.domain.scale import ScaleFormat, ScaleValueKind
from libracore.db.core import Conexion

from ..commerce import repositorio

#: Clave en `commerce_settings`. La balanza esta apagada mientras no exista.
SCALE_FORMAT_KEY = "scale.format"


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
