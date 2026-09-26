"""Los ganchos de VentaLibra para la capa ERP de LibraCommerce (F3, plan
post-P9, ver DECISIONS.md ADR-025).

Acá vive lo que hace a este producto distinto de Contalibra en el núcleo
comercial, expresado como los puntos de extensión que declara
`libracommerce.erp.hooks` -- sin `if producto` en el motor:

- `numerador`: `POS-000001` contra la tabla `sequences` propia (D5: se
  mantiene el prefijo de siempre, ver ADR-005), no `V-00001`.
- `turno_para`: el turno abierto de ESE usuario, en SU caja. Hasta el
  2026-09-16 era compartido (`get_turno_activo_any`, una sola caja para toda
  la instancia); con varias cajas por sucursal cada cajero tiene el suyo
  (ver `app/routers/shifts.py`).
- (`cliente_cc_de` y `nombre_de_cliente` se retiraron el 2026-09-26, migración
  `0004`: desde que `clients.id == parties.id`, como en Contalibra, ya no hay
  nada que traducir.)
- `validar_deposito`: la venta y la devolución salen del depósito de la
  sucursal de la caja del turno (libracommerce v0.17.0). Hasta el 2026-09-17
  lo garantizaba sólo el POS.
"""
from __future__ import annotations

from typing import Any

from libracommerce.erp import Hooks
from libracommerce.erp.catalogo import get_default_deposito_id
from libracommerce.erp.ventas import DepositoNoPermitido
from libracore.db import turnos as db_turnos

from app.db import next_sequence

#: La secuencia propia de este producto para la numeración del punto de
#: venta. Ya existía antes de esta fase (ADR-005); F3 no la cambia, sólo pasa
#: a usarla desde el gancho `numerador` en vez de `services/sales.py`.
SECUENCIA_VENTA = "ventalibra_sale"


def numerador(conn: Any) -> str:
    """`POS-000001`, `POS-000002`, ... D5: se mantiene el prefijo de siempre.

    Usa la MISMA conexión que la transacción de la venta: `next_sequence`
    hace su `UPDATE` con el write-lock ya tomado por esa transacción, igual
    que el numerador default del motor (`erp.ventas.siguiente_numero`) y que
    reintenta en cada intento si el número chocó (`crear_venta_directa`).
    """
    return f"POS-{next_sequence(conn, SECUENCIA_VENTA):06d}"


def turno_para(conn: Any, usuario_id: int | None) -> dict | None:
    """El turno abierto de ESE usuario.

    🔴 **Hasta el 2026-09-16 esto era `get_turno_activo_any()`** (el turno de
    TODA la instancia, compartido): con un solo mostrador no importaba de
    quién era. Con varias cajas por sucursal (cada local vendiendo a la vez)
    eso mezclaba la plata de dos cajeros distintos en el mismo arqueo — es
    exactamente el defecto que esta feature vino a cerrar. Ahora es el
    default del motor (`get_turno_activo`, por cajero), con la misma `conn`
    de la transacción de la venta: es lo que hace que el numerador, el pago y
    el `turno_id` de la venta salgan todos de la misma foto.
    """
    if not usuario_id:
        return None
    return db_turnos.get_turno_activo(int(usuario_id), conn=conn)


def validar_deposito(conn: Any, *, operacion: str, turno: Any | None,
                     deposito_id: int | None) -> None:
    """La venta o la devolución tiene que mover stock del depósito de la
    sucursal de la caja donde está abierto el turno de quien opera.

    🔴 **Hasta el 2026-09-17 esto lo garantizaba sólo el POS**, que fija la
    sucursal a la de la caja apenas hay turno. Un cliente de la API (o un POS
    viejo en otra pestaña) podía mandar el depósito de otro local y el stock de
    las dos sucursales quedaba cruzado sin que nadie lo viera.

    Se compara el depósito **efectivo**: el `deposito_id` que llegó o, si no
    llegó ninguno, el default del motor (`get_default_deposito_id`, el mismo
    que usa `erp.stock.add_movimiento_stock` para resolverlo). Rechazar todo
    `None` habría roto a quien no manda depósito y vende justamente en la
    sucursal default, sin proteger nada más: lo que importa es de DÓNDE sale
    el stock, no si el campo vino.

    No valida con un turno sin caja o una caja sin sucursal: son datos de
    antes de las cajas por sucursal (2026-09-16), y ahí no hay contra qué
    comparar.

    Lee `cajas` y `locations` con la MISMA conexión de la transacción: en
    VentaLibra LibraCore y LibraCommerce comparten base (`_UNA_SOLA_BASE`).
    """
    if not turno or turno.get("caja_id") is None:
        return
    fila = conn.execute(
        "SELECT nombre, sucursal_id FROM cajas WHERE id = ?", (turno["caja_id"],)
    ).fetchone()
    if fila is None or fila[1] is None:
        return
    caja_nombre, sucursal_id = fila[0], int(fila[1])
    efectivo = deposito_id if deposito_id is not None else get_default_deposito_id(conn)
    if efectivo == sucursal_id:
        return
    sucursal = conn.execute(
        "SELECT name FROM locations WHERE id = ?", (sucursal_id,)
    ).fetchone()
    nombre_sucursal = sucursal[0] if sucursal else f"#{sucursal_id}"
    que = "La venta" if operacion == "venta" else "La devolución"
    raise DepositoNoPermitido(
        f"{que} tiene que ser del depósito de la sucursal {nombre_sucursal}: "
        f"el turno está abierto en la caja {caja_nombre}, que es de esa sucursal."
    )


GANCHOS = Hooks(
    numerador=numerador, turno_para=turno_para, validar_deposito=validar_deposito,
)
