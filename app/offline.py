"""La costura de VentaLibra con LibraEdge: lo único del nodo offline que es de este producto (ADR-090).

El nodo offline es la instancia de VentaLibra que corre en la PC del local y sincroniza con el central (el VPS) por
LibraEdge. Desde la fase 1 de LibraEdge en toda la suite (E6, 2026-10-19) todo lo genérico es de los motores: el
aprovisionamiento del central es de LibraEdge (ADR-008, `libraedge-central nodo ...`), las ventas suben por la capa ERP
de LibraCommerce (ADR-067 y ADR-068, `libracommerce.erp.offline`) y la facturación del nodo es de LibraCore (ADR-074,
`libracore.nodo_offline`). Lo que queda acá es declarativo; el modelo es RestoLibra (#511), el primer adoptante.

| Pieza | Qué aporta este producto |
|---|---|
| `aprovisionamiento` | las tablas de referencia (el reparto de autoridad) y las sucursales |
| `OUTBOX` | la identidad del nodo, si está en línea y que la caja de la venta lleva el turno (`caja_con_turno=True`) |
| `GANCHOS_DE_CAJA` | la caja del nodo (turnos y cierre del día) sube al central como operaciones (ADR-091) |
| `altas_en_nodo` | los clientes que se dan de alta en el nodo (id provisorio y `cliente.alta`) suben al central (ADR-092) |
| `offline_stock` | el stock de la sucursal lo mueve sólo el nodo: `stock.movimiento` y `compra.recibida` suben, el central contesta 409, carga inicial (ADR-093) |
| `solo_en_el_central` | la guarda de lo que el nodo no hace: reabrir un día cerrado |
| `compras_solo_en_el_central` | los proveedores y las órdenes de compra se cargan en la web; en el nodo sólo se recibe contra ellas (ADR-093) |
| `CONEXION` / `numerar_en_el_nodo` | en el nodo, facturar con el ticket de ARCA que presta el central |

## Identidad: `LIBRAEDGE_NODE_ID` (y `VENTALIBRA_EDGE_NODE_ID`, por la regla del motor)

`nodo()` es `libraedge.identidad.nodo_actual("VENTALIBRA")`: lee la variable general y la del producto; si están las dos
y difieren, `IdentidadEnConflicto`. Es la **identidad** del nodo (la escribe el instalador). **LibraEdge está incluido en
todos los planes** (decisión del humano, 2026-10-20; libraedge ADR-014): no hay adicional `offline` ni guarda comercial al
registrar un nodo (`sin_guarda`).

El prefijo de numeración (`LIBRAEDGE_PREFIJO`, `S02`) lo asigna el central al registrar el nodo. **Un nodo sin prefijo no
vende**: `NodoLocal` levanta `ValueError` en la primera venta, porque numeraría igual que el central. Con prefijo, la
venta del nodo sale `S02-POS-000123` (el numerador del producto, `POS-`, con el prefijo adelante).

## Aprovisionar (en el central)

    LIBRAEDGE_APROVISIONAMIENTO=app.offline:aprovisionamiento libraedge-central nodo publicar
    libraedge-central nodo sucursales | registrar <node_id> --sucursal <id o nombre> | estado | dar-de-baja <id>
    libraedge-central nodo vigilar --umbral 15
    LIBRAEDGE_DESPACHADOR=app.routers.sincronizacion_offline:despachador libraedge-central revision listar ...

Ver «Nodo offline (LibraEdge)» en `ONBOARDING_CLIENTES.md`.
"""

from __future__ import annotations

import os

from libracommerce.erp import offline_stock
from libracommerce.erp.offline import NodoLocal, Outbox
from libracommerce.erp.offline_caja import caja_con_outbox
from libracommerce.erp.offline_clientes import altas_en_nodo as altas_de_clientes
from libracore import altas_en_nodo
from libracore.altas_en_nodo import REFERENCIAS_DE_CLIENTES
from libracore.ganchos_de_caja import GanchosDeCaja
from libracore.nodo_offline import VARIABLE_ESTADO, ConexionDelNodo, esta_en_linea, guarda_solo_en_el_central
from libraedge.identidad import nodo_actual, prefijo_actual

#: El prefijo de las variables del producto (`VENTALIBRA_DATABASE_URL`, `VENTALIBRA_EDGE_NODE_ID`).
PREFIJO = "VENTALIBRA"

#: El `origen_producto` de la bandeja de comprobantes pendientes y del candado por venta (libracore ADR-074).
PRODUCTO = "ventalibra"

#: El reparto de autoridad: qué tablas manda el central y el nodo sólo espeja. **Sólo los nombres**: la clave la lee
#: LibraEdge de la base (`party_roles` tiene clave compuesta `(party_id, role)`, `units` es `code`, `commerce_settings`
#: es `key`, `modulos` es `modulo`). El porqué de cada una, en DECISIONS.md ADR-090 (y ADR-093 para las de compras).
#:
#: 🔴 NO están `productos`, `categorias_producto`, `listas_precio`, `lista_precio_items` ni `depositos`: existen porque
#: el DDL de LibraCore las crea, pero el catálogo, los precios y los depósitos de este producto viven en LibraCommerce
#: (`catalog_items`, `price_lists`, `item_prices`, `locations`). Tampoco `users` (la tabla propia de antes de libraauth,
#: que ya nadie lee) ni `cuentas_tesoreria` o `item_branch_min_stock`: tesorería y reposición se hacen en el central.
#: **Compras, desde el ADR-093**: los proveedores y las órdenes de compra se cargan en la web y bajan al nodo
#: (`proveedores`, `purchase_orders`, `purchase_order_items`); en el nodo sólo se recibe contra una orden, y la recepción
#: (`purchase_receipts`, de autoridad del nodo) sube como `compra.recibida`. El orden del espejo por FK lo resuelve
#: LibraEdge (`orden_de_siembra`), no esta lista.
#:
#: Las de **autoridad del nodo** (`sales` y sus tablas, `caja_movimientos`, `turnos_caja`, `stock_movements`, `facturas`,
#: la bandeja de comprobantes, `sequences`) no se publican: el nodo las genera y las ventas suben como operaciones. Los
#: lotes no son una tabla: viven en `stock_movements` (`lot_code`). Mercado Pago tampoco se espeja: sin conexión el QR
#: está apagado (libracore ADR-074), y sus credenciales están en el almacén cifrado, no en una tabla de referencia.
TABLAS_DE_REFERENCIA = frozenset({
    # LibraCore y libraauth: la sesión, el gate de módulos y de Términos, las cajas y facturar.
    "usuarios", "aceptaciones_terminos", "modulos", "clients", "cajas", "arca_config",
    # LibraCommerce: lo que lee el POS para vender.
    "branches", "locations", "units", "categories", "catalog_items", "item_variants", "item_codes",
    "price_lists", "item_prices", "cliente_lista_precio", "promotions", "promotion_items", "commerce_settings",
    "parties",
    # Compras (ADR-093): se cargan en la web y bajan; el nodo recibe contra la orden. El party de cada proveedor
    # (`id = proveedores.id + 100000`) baja por `parties`.
    "proveedores", "purchase_orders", "purchase_order_items",
    # Propias de VentaLibra (extensiones de `parties`).
    "party_roles", "party_billing",
})


# ── La identidad y la conexión del nodo ─────────────────────────────────────────────────────────────────────────────


def nodo() -> str | None:
    """El id de este nodo, o `None` si la instancia no es un nodo offline (el central, o una instalación común).

    Se lee en cada llamada: activar el nodo no exige reiniciar nada y la suite no depende del orden de los tests."""
    return nodo_actual(PREFIJO)


def nodo_local() -> NodoLocal | None:
    """La identidad de este nodo con su prefijo de numeración, para el outbox de LibraCommerce."""
    node_id = nodo()
    if node_id is None:
        return None
    return NodoLocal(node_id=node_id, prefijo=prefijo_actual() or "")


def en_linea() -> bool:
    """Si el nodo ve al central: lo que dice el archivo de estado del proceso del nodo (`LIBRAEDGE_ESTADO`).

    Es la de libracore (ADR-074): el último ciclo sincronizó y la última sincronización buena es reciente. Sin archivo,
    viejo o ilegible, sin conexión. La ruta se lee en cada llamada (`conexion_desde_entorno` la congela al armarse)."""
    return esta_en_linea((os.environ.get(VARIABLE_ESTADO) or "").strip() or None)


#: Lo que LibraCore pregunta antes de salir a ARCA o a MercadoPago (va en el `PuertoDeVentas`). Fuera de un nodo,
#: nada cambia.
CONEXION = ConexionDelNodo(nodo=nodo, en_linea=en_linea)

#: El outbox de LibraEdge para `libracommerce.erp.offline.con_outbox`. El mismo en el nodo y en el central: fuera de un
#: nodo (`nodo_local()` es `None`) no encola nada. Sin `extra_de_venta`: la venta de mostrador de VentaLibra no lleva
#: nada propio que el central necesite (el turno viaja como dato en `turno_id_nodo`).
#:
#: 🔑 `caja_con_turno=True`: VentaLibra escribe el turno en los movimientos de caja de la venta (`registrar_venta`,
#: `anular_venta`, `devolver_items` y `acreditar_pago_qr` van con `caja_con_turno=True`, `app/db_ventas.py` y
#: `OpcionesVentas` en `app/main.py`), así que el central tiene que hacer lo mismo para que el arqueo del turno dé igual en
#: las dos puntas (libracommerce ADR-069).
OUTBOX = Outbox(nodo=nodo_local, en_linea=en_linea, caja_con_turno=True)

#: Las altas de clientes en un nodo (libracore ADR-077, libracommerce ADR-070, ADR-092 de este producto): en un nodo,
#: `POST /api/clientes` (y cualquier alta de `libracore.db.clients`) guarda al cliente con un **id provisorio negativo** y
#: encola `cliente.alta` en el `OUTBOX`, en la misma transacción del alta; el central le asigna su id y las ventas
#: posteriores a ese cliente suben traducidas (`venta.registrada`). Se registra al importar este módulo, que importa la app
#: (`app/main.py`) y el CLI del central (`LIBRAEDGE_APROVISIONAMIENTO`): en las dos puntas. **Fuera de un nodo**
#: (`nodo_local()` es `None`) el motor no pide ids provisorios ni avisa a nadie, y el alta es la de siempre.
altas_en_nodo.configurar(altas_de_clientes(OUTBOX))

#: Los ganchos de la caja para `build_turnos_router` y `build_cierre_diario_router` (`ganchos_de_caja=`): en un nodo
#: encolan en el `OUTBOX` el turno que se abre o se cierra y el cierre del día (libracore ADR-076, libracommerce ADR-069);
#: **fuera de un nodo** (`nodo_local()` es `None`) no hacen nada, como `GanchosDeCaja()`. Se pasan por llamada y no se
#: registran globalmente: la caja de una venta no sube acá sino con la venta (`venta.registrada`, `venta.pago_acreditado`,
#: `venta.anulada`, `venta.devolucion`); si además subiera como `caja.movimiento` quedaría duplicada en el central. Este
#: producto no monta `build_caja_router` (no hay ingresos ni egresos a mano): `caja.movimiento` y
#: `caja.movimiento_anulado` no se encolan nunca acá. Mismos ganchos en el central: el despachador de
#: `app/routers/sincronizacion_offline.py` ya registra todos los tipos (`registrar_en`; con `cliente.alta`, once).
GANCHOS_DE_CAJA = caja_con_outbox(GanchosDeCaja(), OUTBOX)

#: El stock de la sucursal de un nodo (libracommerce ADR-071, ADR-093 de este producto): desde la carga inicial **lo mueve
#: sólo el nodo**. `configurar` arma las dos mitades en el proceso, una vez y en las dos puntas (como `altas_en_nodo`): en un
#: nodo encola `stock.movimiento` por cada fila del ledger que no viaja con una venta ni con una recepción, y en el central
#: se niega (`DepositoDeSucursalConNodo`, 409 por `offline_stock.instalar_manejador_409(app)` en `app/main.py`) a mover un
#: depósito de una sucursal con nodo activo. La recepción de compras sube por `OpcionesCompras(al_recibir=...)`
#: (`app/compras_ganchos.py`). Fuera de un nodo y de una sucursal con nodo no cambia nada.
offline_stock.configurar(OUTBOX)

#: Lo que el nodo no hace: `Depends(solo_en_el_central)` contesta 409 `solo_en_el_central` en un nodo y no hace nada en el
#: central ni en una instalación común. La identidad se lee en cada pedido (`nodo()`, que mira las dos variables).
solo_en_el_central = guarda_solo_en_el_central(nodo=nodo)

#: Lo mismo, con el motivo de las compras (ADR-093): los proveedores y las órdenes de compra se cargan en la versión web y bajan
#: al nodo por el espejo; el nodo sólo recibe mercadería contra una orden ya cargada. Es el mensaje que ve quien lo intenta.
MENSAJE_COMPRAS_SOLO_EN_EL_CENTRAL = "Las órdenes de compra y los proveedores se cargan en la versión web."
compras_solo_en_el_central = guarda_solo_en_el_central(nodo=nodo, mensaje=MENSAJE_COMPRAS_SOLO_EN_EL_CENTRAL)


# ── Facturar en el nodo con el ticket prestado ──────────────────────────────────────────────────────────────────────

_cliente_de_ticket = None


def _version_esquema_del_nodo() -> str | None:
    """La misma versión de esquema que manda el proceso del nodo (`LIBRAEDGE_VERSION_ESQUEMA`, `alembic` por defecto),
    para que el central conteste 409 si no coinciden."""
    from libracore.db.core import get_connection
    from libraedge.cli import version_esquema_del_nodo

    with get_connection() as conn:
        return version_esquema_del_nodo(conn, os.environ.get("LIBRAEDGE_VERSION_ESQUEMA"))


def cliente_de_ticket():
    """El `ClienteDeTicket` de LibraEdge de este nodo (uno por proceso: guarda el ticket en memoria hasta que vence).
    Lo arma recién al primer uso: fuera de un nodo no hay a quién pedirle y `cliente_desde_entorno` levantaría."""
    global _cliente_de_ticket
    if _cliente_de_ticket is None:
        from libraedge.sync.ticket import cliente_desde_entorno

        version: list[str | None] = []

        def version_esquema() -> str | None:
            if not version:
                version.append(_version_esquema_del_nodo())
            return version[0]

        _cliente_de_ticket = cliente_desde_entorno(version_esquema=version_esquema)
    return _cliente_de_ticket


def obtener_ta_del_central():
    """El `obtener_ta(arca)` de `libracore.nodo_offline.numerador_con_ta`, sobre el transporte de LibraEdge.

    Un corte (sin red, 5xx, esquema distinto) llega como `SinConexion` y la venta va a la bandeja. Un **rechazo** del
    central (`TicketRechazado`: nodo revocado, sin ARCA, sin la ruta) se traduce a `RechazoDelCentral`: 422
    `nodo_sin_arca`, no va a la bandeja (no se arregla solo al volver la conexión)."""
    from libracore.nodo_offline import RechazoDelCentral, SinConexion
    from libraedge.sync.ticket import TicketRechazado

    base = cliente_de_ticket().para_numerador(sin_conexion=SinConexion)

    async def obtener_ta(arca: dict) -> dict:
        try:
            return await base(arca)
        except TicketRechazado as e:
            raise RechazoDelCentral(
                "El central no presta el ticket de ARCA a este equipo (nodo revocado o sin credencial).") from e

    return obtener_ta


async def numerar_en_el_nodo(punto_venta: int, tipo: int) -> tuple:
    """El `numerar_comprobante` de un nodo: el número de ARCA pedido con el ticket que presta el central. Nunca numera
    local (ese número chocaría con el de ARCA y con el del central)."""
    from libracore.nodo_offline import numerador_con_ta

    return await numerador_con_ta(obtener_ta_del_central())(punto_venta, tipo)


# ── El aprovisionamiento del central ────────────────────────────────────────────────────────────────────────────────


def _conectar():
    """La base de la instancia, para el CLI de LibraEdge (que corre sin la app): la misma URL que arma `app/asgi.py`.
    En VentaLibra el dominio y LibraCore son la misma base (`_UNA_SOLA_BASE`)."""
    from libracore.db.core import conectar
    from libracore.db.url_de_instancia import url_de_instancia

    return conectar(url_de_instancia("ventalibra", requerida=True))


def sucursales_con_nodo() -> int:
    """Cuántas sucursales distintas tienen un nodo activo, con su propia conexión (hasta ADR-014 la medía el router de
    adicionales; LibraEdge ya no es un adicional, queda para quien la consulte)."""
    from libracore.db.core import get_connection
    from libraedge.aprovisionamiento import sucursales_con_nodo as contar

    with get_connection() as conn:
        return contar(conn)


def nodos_del_central() -> list[dict]:
    """Los nodos registrados en esta instancia, para la barra de estado del pie (libracore ADR-075): la misma lista que
    «Sucursal sin internet» (`libraedge.pantalla_del_central.nodos_de_la_instancia`, sin el hash del secreto). El motor
    usa sólo `activo` y `estado`."""
    from libracore.db.core import get_connection
    from libraedge.pantalla_del_central import nodos_de_la_instancia

    with get_connection() as conn:
        return nodos_de_la_instancia(conn, [])


def _listar_sucursales(conn) -> list[dict]:
    from libracommerce.erp.catalogo import get_all_sucursales

    return get_all_sucursales(conn)


def _aprovisionamiento():
    from libraedge.aprovisionamiento import Aprovisionamiento, sin_guarda

    return Aprovisionamiento(
        prefijo=PREFIJO, tablas_de_referencia=TABLAS_DE_REFERENCIA, listar_sucursales=_listar_sucursales,
        # Los clientes se dan de alta en el nodo (id provisorio, ADR-092): `clients` con lo que lo referencia sin FK
        # (`cc_asientos.tercero_id`) y su `parties` espejo, que es a lo que apunta `sales.customer_party_id`.
        altas_en_nodo=[("clients", REFERENCIAS_DE_CLIENTES), "parties"],
        # Sin guarda comercial: LibraEdge está incluido en todos los planes (libraedge ADR-014).
        verificar_alta=sin_guarda, conectar=_conectar,
        # Un depósito sin sucursal no es de ningún nodo: la guarda del central no lo ve y la carga inicial no lo trae
        # (libracommerce ADR-071, libraedge ADR-023). Registrar un nodo se niega hasta que cada depósito tenga sucursal.
        validar_registro=offline_stock.depositos_sin_sucursal,
    )


#: Lo que el central necesita para aprovisionar los nodos de este producto (`LIBRAEDGE_APROVISIONAMIENTO`).
aprovisionamiento = _aprovisionamiento()
