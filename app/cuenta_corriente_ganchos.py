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
  `cc_pagos`): es lo que permite darle de baja al pago, buscando el ingreso por esa referencia;
- la baja de un pago **anula** (no borra: pedido del humano, 2026-08-28) el movimiento de caja; un pago cuyo
  movimiento no se puede identificar se rechaza (409) en vez de dejar un ingreso huérfano en el arqueo.
"""
from fastapi import HTTPException
from libracore import medios_pago
from libracore.cuenta_corriente_router import CobroAprobado, OpcionesCuentaCorriente
from libracore.db import caja as db_caja
from libracore.db import cuenta_corriente as db_cc
from libracore.db import turnos as db_turnos

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
    """Anula el movimiento de caja del pago, buscándolo por su referencia. Si no lo encuentra, 409."""
    pago = db_cc.get_cc_pago(pago_id)
    if pago is None:
        raise HTTPException(404, f"no existe el pago {pago_id}")
    tag = REFERENCIA_DEL_PAGO.format(pago_id=pago_id)
    movimientos = [
        m for m in db_caja.get_caja_movimientos(desde=pago["fecha"], hasta=pago["fecha"], limit=500)
        if m["referencia"] == tag
    ]
    if not movimientos:
        raise HTTPException(
            409,
            f"el pago {pago_id} no tiene un movimiento de caja identificable: "
            "no se da de baja automáticamente",
        )
    for movimiento in movimientos:
        db_caja.anular_caja_movimiento(movimiento["id"])


OPCIONES = OpcionesCuentaCorriente(
    validar_pago=validar_pago, cajas=cajas_del_turno, al_eliminar_pago=al_eliminar_pago,
)
