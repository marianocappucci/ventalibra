"""Compras (órdenes y recepciones) de VentaLibra sobre el router del motor.

Desde la fase 9 de la adopción de los motores (2026-09-27, ADR-036) VentaLibra monta
`libracommerce.web.compras_router.build_compras_router`, extraído del propio
`app/routers/purchasing.py` y `app/services/purchasing.py` de este producto (era el único que lo tenía
montado: `libracommerce` v0.21.0). Lo que hace distinto a VentaLibra son dos ganchos, no reglas de negocio:

- **la numeración**: `next_sequence(conn, "ventalibra_purchase_order")`, atómica dentro de la misma
  transacción (a diferencia del `MAX(id)+1` sin lock del motor, pensado para baja concurrencia);
- **el `proveedor_id`**: VentaLibra guarda los proveedores en su propia tabla (`libracore.db.egresos`,
  ADR-030) con un id que NO es el `party_id` que exige la FK de compras — la traducción, en los dos
  sentidos, ya vivía en `app/services/proveedores.py` (`party_de_proveedor`/`proveedor_de_party`,
  offset `+100.000`) y se reusa acá tal cual.

## En un nodo offline (ADR-093)

Los proveedores y las órdenes de compra se cargan en la versión web y bajan al nodo por el espejo; **en el nodo sólo se recibe
contra esas órdenes** (lote, vencimiento y costo) y la recepción sube al central como `compra.recibida`:

- `al_recibir=offline_stock.recepcion_con_outbox(OUTBOX)` encola esa operación dentro de la transacción de la recepción. Fuera de
  un nodo no hace nada.
- `compras_del_nodo` (dependencia del `include_router`) deja en 409 `solo_en_el_central` crear, cargar, enviar y cancelar órdenes
  y el flujo de recepción de tres pasos (crear, cargar líneas, confirmar). Queda `POST /api/purchase-receipts/recibir`, y sólo con
  `purchase_order_id`: una recepción sin orden es 409 `recepcion_sin_orden`.
- `_resolver_proveedor` no escribe `parties` en un nodo: verifica que el party del proveedor haya bajado
  (`app/services/proveedores.py`) y, si no, 409 `proveedor_sin_sincronizar`.

`autorizar_escritura` no se pasa: como en depósitos y productos, el `requiere_segun_ruta(...)` con el
que este producto monta el router entero ya cubre lectura y escritura por capacidad (`compras.ver`,
`compras.escribir` y `compras.recibir`, ADR-049).
"""
from __future__ import annotations

import re

from fastapi import HTTPException, Request
from libracommerce.erp import offline_stock
from libracommerce.web.compras_router import OpcionesCompras

from .db import next_sequence
from .offline import OUTBOX, compras_solo_en_el_central, nodo
from .services.proveedores import (
    ProveedorNoExiste,
    ProveedorSinSincronizar,
    party_de_proveedor,
    proveedor_de_party,
)


def _numerador(conn) -> str:
    return f"OC-{next_sequence(conn, 'ventalibra_purchase_order'):06d}"


def _resolver_proveedor(conn, proveedor_id: int) -> int:
    try:
        return party_de_proveedor(conn, proveedor_id)
    except ProveedorNoExiste as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProveedorSinSincronizar as exc:
        raise HTTPException(409, {"codigo": "proveedor_sin_sincronizar", "mensaje": str(exc)}) from exc


def _proveedor_de(_conn, party_id: int) -> int:
    return proveedor_de_party(party_id)


#: Los mismos ganchos, con nombres para otros routers del motor que hablan de proveedores (la reposición, ADR-056): el `proveedor_id` que ve
#: el usuario es el de la tabla de VentaLibra y el motor guarda y compara por `party_id`.
resolver_proveedor_del_producto = _resolver_proveedor
proveedor_del_producto = _proveedor_de


OPCIONES_DE_COMPRAS = OpcionesCompras(
    numerador=_numerador, resolver_proveedor=_resolver_proveedor, proveedor_de=_proveedor_de,
    # En un nodo la recepción sube como `compra.recibida` (libracommerce ADR-071). Sin esto las filas de la recepción no subirían
    # ni como movimiento ni como compra y el stock del central no se enteraría.
    al_recibir=offline_stock.recepcion_con_outbox(OUTBOX),
)

#: Lo que el nodo no escribe de Compras: las órdenes (crear, cargar líneas, enviar, cancelar) y la recepción en tres pasos.
_ORDENES = re.compile(r"^/api/purchase-orders(/.*)?$")
_RECEPCION_EN_TRES_PASOS = re.compile(r"^/api/purchase-receipts(/\d+/(items|confirm))?$")
_RECIBIR = "/api/purchase-receipts/recibir"


async def compras_del_nodo(request: Request) -> None:
    """Dependencia del `include_router` de Compras (ADR-093). En un nodo: 409 `solo_en_el_central` para lo que escribe órdenes o la
    recepción en tres pasos, y «Recibir mercadería» sólo contra una orden. Fuera de un nodo, y para las lecturas, no hace nada."""
    if nodo() is None or request.method in ("GET", "HEAD", "OPTIONS"):
        return
    ruta = request.url.path.rstrip("/")
    if _ORDENES.match(ruta) or _RECEPCION_EN_TRES_PASOS.match(ruta):
        compras_solo_en_el_central()
    elif ruta == _RECIBIR:
        try:
            cuerpo = await request.json()
        except ValueError:
            return                                     # un cuerpo ilegible lo rechaza la validación del motor (422)
        if not isinstance(cuerpo, dict) or not cuerpo.get("purchase_order_id"):
            raise HTTPException(409, {
                "codigo": "recepcion_sin_orden",
                "mensaje": "En este equipo la mercadería se recibe contra una orden de compra cargada en la versión web.",
            })


__all__ = ["OPCIONES_DE_COMPRAS", "compras_del_nodo", "proveedor_del_producto", "resolver_proveedor_del_producto"]
