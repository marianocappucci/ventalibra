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

🔴 **`obtener` traduce `cliente_id` de `party_id` a `clients.id` -- si no,
la factura sale con los datos de OTRO cliente.** `libracore.venta_facturacion.
facturar_venta` resuelve el cliente con `db_clients.get_client(venta[
"cliente_id"])`, y ese `cliente_id` es `sales.customer_party_id`: un `parties.
id` de LibraCommerce, no un `clients.id` de LibraCore. Acá los dos NO
coinciden (D3, ADR-025; medido en `ventalibra-dev`: los `clients` 1-3 son
personas distintas de los `parties` 1-3), así que pasarlo derecho hacía que
`get_client` devolviera el cliente que casualmente tuviera ese número de id
-- o ninguno-- en vez del que vendió. Se traduce con el MISMO criterio que
`app/ganchos.py::cliente_cc_de` (reusada, no reescrita): `clients.external_ref
= 'party-<id>'`. Es una lectura-o-alta igual que esa función -- ver su
docstring --, así que una venta facturada a un cliente que nunca fió también
le crea (o reusa) su fila en `clients`; antes de este fix esa fila sólo nacía
al fiar.

Se envuelve `db_ventas.PUERTO.obtener`, no el de `libracore.venta_facturacion`
(ese es el consumidor, no el dueño del dato): el `PUERTO` de acá es el que
`app/main.py` pasa a `libracore.ventas_cobro_router.build_cobro_de_ventas_router`
(`/mp-qr`, `/mp-status`, `/facturar`) -- los tres usos de `obtener` en ese router
(`_venta_o_404`, y el `"venta"` que devuelve `POST .../facturar`) sólo leen
`numero`, `items`, `total`, `mp_payment_id`, `factura_id`: ninguno mira
`cliente_id`, salvo el `"venta"` de la respuesta de `/facturar`, que pasa a
mostrar el `clients.id` en vez del `party_id` -- no hay test que dependa de
ese valor puntual, y es el mismo dato que ya se traduce en cualquier otra
lectura de cuenta corriente (`app/services/cuenta_corriente.py`). `GET
/api/ventas/{vid}` (LibraCommerce, `db_ventas.PUERTO` sin envolver) sigue
devolviendo el `party_id` sin tocar -- ver `app/main.py`.
"""
import dataclasses

from libracore import arca_facturacion
from libracore.db.core import get_connection as _lc_get_connection
from libracore.venta_facturacion import (  # noqa: F401
    CONSUMIDOR_FINAL,
    IVA_RATE_DEFAULT,
    VentaNoFacturable,
)

from app import db_ventas
from app.ganchos import cliente_cc_de


async def _numerar(punto_venta: int, tipo: int):
    return await arca_facturacion.get_next_numero_with_arca(punto_venta, tipo)


def _obtener_con_cliente_traducido(venta_id: int) -> dict | None:
    """`db_ventas.PUERTO.obtener`, con `cliente_id` traducido -- ver el 🔴
    del docstring del módulo."""
    venta = db_ventas.PUERTO.obtener(venta_id)
    if venta is None or venta.get("cliente_id") is None:
        return venta
    with _lc_get_connection() as conn:
        cliente_id = cliente_cc_de(conn, venta)
    return {**venta, "cliente_id": cliente_id}


#: El puerto completo de este producto: las ventas de `db_ventas` (con
#: `cliente_id` traducido) más el numerador. Es el que montan el router del
#: cobro y el webhook (a futuro).
PUERTO = dataclasses.replace(
    db_ventas.PUERTO, numerar_comprobante=_numerar, obtener=_obtener_con_cliente_traducido,
)
