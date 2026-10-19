"""El central expone la sincronización del nodo offline: `/sync/v1/push`, `/sync/v1/pull` y `/sync/v1/ticket-arca`.

E6 de LibraEdge (2026-10-19, ADR-090). Es el mismo armado que RestoLibra (#511), sin la compatibilidad de su piloto:
VentaLibra nunca tuvo un nodo, así que no hay operaciones viejas que aplicar.

## Por qué se monta siempre, y no sólo en las instancias con nodos

El gateo está del otro lado: sin un nodo registrado **no existe ningún secreto válido**, así que en una instancia sin
nodos las rutas responden 401 a todo. Montarlas condicionalmente agregaría una bandera más que puede quedar mal puesta,
y el modo de fallar sería el peor posible: un nodo instalado que no puede sincronizar contra un central que «debería»
tener el endpoint.

## La conexión es por request

Se le pasa `libracore.db.core.get_connection` —la fábrica del motor, la misma que usan `build_ventas_router` y
`app/db_ventas.py`— y no una conexión armada: el router abre una por request (ver `create_sync_router` en LibraEdge).
En VentaLibra el dominio y LibraCore son la misma base, así que esa conexión ve `sales` y `node_identity` a la vez.

## Qué se aplica

Un `Despachador` (libraedge ADR-007) con las cinco operaciones de venta de la capa ERP (`venta.registrada`,
`venta.pago_acreditado`, `venta.anulada`, `venta.devolucion`, `venta.facturada`; libracommerce ADR-067 y ADR-068), con
los ganchos del producto. Lo que no tiene aplicador **no se marca aplicado**: va a revisión manual
(`libraedge-central revision listar|reintentar|descartar`, con
`LIBRAEDGE_DESPACHADOR=app.routers.sincronizacion_offline:despachador`).

El router además controla la versión del esquema (`version_de_alembic`: 409 si el nodo no está migrado igual que el
central) y le presta al nodo el ticket de ARCA (`libracore.nodo_offline.ta_para_el_nodo`, libraedge ADR-009): la clave
no sale del VPS.
"""

from libracommerce.erp.offline import registrar_en
from libracore.db.core import get_connection
from libracore.nodo_offline import ta_para_el_nodo
from libraedge.sync.api import create_sync_router
from libraedge.sync.despacho import Despachador
from libraedge.sync.esquema import version_de_alembic

from app.ganchos import GANCHOS


def armar_despachador() -> Despachador:
    """Las operaciones que el central de VentaLibra sabe aplicar."""
    return registrar_en(Despachador(), GANCHOS)


despachador = armar_despachador()

router = create_sync_router(
    get_connection, despachador=despachador, version_esquema=version_de_alembic,
    prestar_ticket=ta_para_el_nodo,
)
