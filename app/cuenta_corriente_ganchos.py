"""Las reglas de cobro de VentaLibra sobre el router de cuenta corriente del motor.

Desde la fase 4 de la adopción de los motores (2026-09-26, ADR-031) VentaLibra monta
`libracore.cuenta_corriente_router.build_cuenta_corriente_router`, el mismo de Contalibra y Restolibra, y
declara acá lo que lo hace distinto como `OpcionesCuentaCorriente` (`libracore` v1.111.0). Son las reglas de
ADR-027, que ya no viven en un router propio:

- el cobro **exige turno abierto** (409) y cae en la **caja del turno** de quien cobra: el arqueo de este
  producto es por turno;
- si `caja_id` viene y no es la del turno, 422: un pago quedaría anotado en una caja cuyo arqueo no lo cuenta;
- el selector de caja ofrece **sólo la caja del turno**;
- `cuenta_corriente` no es un medio de cobro (422): es la marca de que la operación se hizo a crédito;
- el movimiento de caja lleva SIEMPRE la referencia `cc-pago-<id>` (la que escribió el usuario vive en
  `cc_pagos`): sirve de rastro y es de donde sale el backfill de `cc_pago_id` (la baja ya no busca por texto);
- la baja de un pago **anula** (no borra: pedido del humano, 2026-08-28) sus movimientos de caja, y eso lo hace el
  motor por `cc_pago_id` desde `libracore` v1.117.0; acá queda la regla de que un pago cuyo movimiento no se puede
  identificar se rechaza (409) en vez de dejar un ingreso huérfano en el arqueo.
"""
from fastapi import HTTPException
from libracore import medios_pago
from libracore.cuenta_corriente_router import CobroAprobado, OpcionesCuentaCorriente
from libracore.db import caja as db_caja
from libracore.db import cuenta_corriente as db_cc
from libracore.db import turnos as db_turnos
from libracore.db.core import get_connection

#: Plantilla de la referencia del movimiento de caja de un pago a cuenta.
REFERENCIA_DEL_PAGO = "cc-pago-{pago_id}"


def validar_pago(payload, user: dict) -> CobroAprobado:
    if payload.monto <= 0:
        raise HTTPException(422, "el monto a cobrar debe ser mayor que cero")
    if payload.medio_pago == "cuenta_corriente":
        raise HTTPException(422, "la cuenta corriente no es un medio para cobrar una deuda")
    try:
        medios_pago.validar(payload.medio_pago)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    turno = db_turnos.get_turno_activo(int(user["id"])) if user else None
    if turno is None:
        raise HTTPException(409, "no hay un turno de caja abierto")
    if payload.caja_id is not None and payload.caja_id != turno.get("caja_id"):
        raise HTTPException(422, "la cobranza cae en la caja del turno abierto")
    return CobroAprobado(
        caja_id=turno.get("caja_id"), turno_id=turno["id"], referencia_movimiento=REFERENCIA_DEL_PAGO,
    )


def cajas_del_turno(user: dict) -> list[dict]:
    """La caja del turno abierto de quien consulta, y sólo esa. Sin turno, lista vacía: el selector se
    oculta y el cobro va a chocar con el 409."""
    turno = db_turnos.get_turno_activo(int(user["id"])) if user else None
    if turno is None or not turno.get("caja_id"):
        return []
    return [c for c in db_caja.get_all_cajas() if c["id"] == turno["caja_id"]]


def al_eliminar_pago(pago_id: int, user: dict) -> None:
    """Rechaza la baja si el pago no tiene ningún movimiento de caja identificable (409).

    Anular esos movimientos ya no es de acá: `libracore` v1.117.0 lo hace en el motor, por `cc_pago_id`, para todos
    los productos. Este gancho sólo conserva la regla de VentaLibra —un pago cuyo movimiento no se puede identificar
    no se da de baja, para no dejar un ingreso huérfano en el arqueo—. Los pagos anteriores al motor se ligan con el
    backfill de `app/cc_pago_backfill.py` (migración `0008`)."""
    pago = db_cc.get_cc_pago(pago_id)
    if pago is None:
        raise HTTPException(404, f"no existe el pago {pago_id}")
    with get_connection() as conn:
        hay = conn.execute(
            "SELECT 1 FROM caja_movimientos WHERE cc_pago_id = ? LIMIT 1", (pago_id,)
        ).fetchone()
    if hay is None:
        raise HTTPException(
            409,
            f"el pago {pago_id} no tiene un movimiento de caja identificable: "
            "no se da de baja automáticamente",
        )


OPCIONES = OpcionesCuentaCorriente(
    validar_pago=validar_pago, cajas=cajas_del_turno, al_eliminar_pago=al_eliminar_pago,
)
