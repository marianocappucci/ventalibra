"""Shim: la factura desde la venta vive en `libracore.venta_facturacion`
desde F3 del plan post-P9 (2026-09-14), sobre el `PuertoDeVentas` de
`app/db_ventas.py`.

🔴 **`arca_facturacion` se importa como MÓDULO, no el nombre suelto** --a
diferencia de Contalibra/Restolibra, que importan `get_next_numero_with_arca`
directo en su propio shim. La convención de ESTE repo es la del camino
legado (`app/services/billing.py::invoice_sale`, `from libracore import
arca_facturacion; ... arca_facturacion.get_next_numero_with_arca(...)`), y
`tests/test_la_factura_declara_su_ambiente.py` ya parchea
`arca_facturacion.get_next_numero_with_arca` con esa forma. Un import directo
del nombre habría dejado ese monkeypatch sin efecto acá: el atributo del
módulo se relee en cada llamada, un `from ... import nombre` congela la
referencia al importar.

🔴 No reemplaza a `app/services/billing.py` (la facturación del camino
LEGACY, `/sales/{id}/confirm`, IVA fijo al 21%): ese endpoint queda de sólo
lectura desde F3 (ver `app/routers/sales.py`), pero el módulo sigue vivo
porque `GET /sales/{id}/ticket` y el resto de las lecturas de ventas viejas
lo pueden necesitar indirectamente. Este módulo es del camino NUEVO
(`/api/ventas/{id}/facturar`), con las alícuotas de `venta_facturacion`
(D6/plan: ya no IVA fijo).

**`cliente_id` ya no se traduce** (2026-09-26, migración `0004`): `libracore.venta_facturacion.
facturar_venta` resuelve el cliente con `db_clients.get_client(venta["cliente_id"])`, y desde que
VentaLibra sigue la convención de Contalibra (`clients.id == parties.id`) el `cliente_id` de la
venta (`sales.customer_party_id`) ES el `clients.id`. Antes había que traducirlo por `external_ref`
o la factura salía con los datos de otro cliente.
"""
import dataclasses

from libracore import arca_facturacion
from libracore.venta_facturacion import (  # noqa: F401
    CONSUMIDOR_FINAL,
    IVA_RATE_DEFAULT,
    VentaNoFacturable,
)

from app import db_ventas


async def _numerar(punto_venta: int, tipo: int):
    return await arca_facturacion.get_next_numero_with_arca(punto_venta, tipo)


#: El puerto completo de este producto: las ventas de `db_ventas` más el numerador. Es el
#: que montan el router del cobro y el webhook (a futuro).
PUERTO = dataclasses.replace(db_ventas.PUERTO, numerar_comprobante=_numerar)
