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
- `cliente_cc_de`: traduce `customer_party_id` (`parties.id` de
  LibraCommerce) al `clients.id` de LibraCore por `external_ref = party-<id>`
  -- acá los dos ids NO coinciden (D3, ADR-025), a diferencia de Contalibra
  donde son el mismo id.
"""
from __future__ import annotations

from typing import Any

from libracommerce.erp import Hooks
from libracore.db import clients as db_clients
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


def cliente_cc_de(conn: Any, venta: Any) -> int | None:
    """El `clients.id` de LibraCore para la cuenta corriente de esta venta.

    Mismo criterio que `services/cuenta_corriente.py::CuentaCorrienteService.
    _cliente_cc`: el cliente de la venta es una `party` de LibraCommerce, y
    acá se traduce por `external_ref = party-<id>` -- crea el `clients.id` la
    primera vez que ese party fía y lo reusa siempre. No espeja la cartera:
    sólo entra quien efectivamente fía.

    🔴 `resolver_cliente_externo` abre su PROPIA conexión (no acepta
    `conn=`): la creación/actualización del `clients.id` no queda dentro de
    la transacción de la venta. Es una limitación heredada del motor, no
    introducida acá -- el código de hoy (`CuentaCorrienteService._cliente_cc`)
    tiene exactamente la misma característica.
    """
    party_id = venta.get("cliente_id")
    if party_id is None:
        return None
    row = conn.execute(
        "SELECT display_name, tax_id, email, phone FROM parties WHERE id = ?",
        (party_id,),
    ).fetchone()
    if row is None:
        return None
    return db_clients.resolver_cliente_externo(
        f"party-{party_id}", row[0], cuit_dni=row[1] or "", email=row[2] or "", phone=row[3] or "",
    )


GANCHOS = Hooks(numerador=numerador, turno_para=turno_para, cliente_cc_de=cliente_cc_de)


def nombre_de_cliente(party_id: int) -> str | None:
    """El `display_name` del party elegido en `POST /api/ventas`, para el
    snapshot de `sales.customer_name_snapshot`.

    No es un gancho de `Hooks` -- es `OpcionesVentas.nombre_de_cliente`
    (`libracommerce.web.ventas_router`), que llama con sólo el id, sin la
    conexión de la venta (por eso abre la suya, como `cliente_cc_de`). El
    default del motor busca en `clients` (`libracore.db.clients.get_client`):
    en VentaLibra `cliente_id` es un `party_id` de LibraCommerce, no un
    `clients.id`, así que ese default siempre da `None` y la venta queda con
    `cliente_nombre = ""` aunque sí tenga cliente.
    """
    from libracore.db.core import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT display_name FROM parties WHERE id = ?", (party_id,)
        ).fetchone()
    return row[0] if row else None
