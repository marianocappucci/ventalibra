"""Contrato del kit para la cuenta corriente: `/api/cuenta-corriente`.

Las pantallas del kit (`libra-ui/comercio/CuentaCorriente` +
`CuentaCorrienteDetalle`, las mismas que montan Contalibra y Restolibra desde
P9-M4) hablan con el producto por rutas fijas. El negocio ya estaba en
`/accounts` + `CuentaCorrienteService`; acá se expone el contrato que el kit
espera, conservando las reglas de VentaLibra:

- el cobro **exige turno abierto** y cae en la caja del turno de quien cobra
  (el arqueo de este producto es por turno; mismo criterio que
  `POST /accounts/{party_id}/payments`);
- el selector de caja del kit ofrece **sólo la caja del turno** propio, no
  todas: en este producto el ingreso siempre cae en la caja del turno de quien
  cobra, así que ofrecer las demás sería ofrecer algo que el backend no honra;
- si `caja_id` viene y no es la caja del turno, 422 -- sin esto un pago
  quedaría anotado en una caja cuyo arqueo no lo cuenta;
- `cuenta_corriente` no es un medio de cobro (mismo criterio que
  `CobranzaIn` en `app/routers/accounts.py`);
- los montos van como números (`float`), no `Decimal`-string: el kit compara
  `saldo > 0` y suma montos en el navegador (el router `/accounts` serializa
  Decimal y su pantalla propia convertía con `Number()` al mostrar).

La baja de pago es admin-only, anula el recibo y anula (no borra) el
movimiento de caja; ver `CuentaCorrienteService.eliminar_pago`.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from libracore import medios_pago
from libracore.db import caja as db_caja
from libracore.db import turnos as db_turnos
from pydantic import BaseModel, field_validator

from ..auth import get_current_user, require_admin
from ..services.cuenta_corriente import (
    CuentaCorrienteService,
    SinCliente,
    SinMovimientoDeCaja,
    SinPago,
)
from . import accounts

router = APIRouter(prefix="/api/cuenta-corriente", tags=["cuenta_corriente"])

# El kit trae sus rutas de recibos (`POST /api/recibos/cobranza/{id}` y
# `GET /api/recibos/{id}/pdf`); son las mismas operaciones de
# `/accounts/receipts/...`, servidas en la ruta que llaman las pantallas.
router_recibos = APIRouter(prefix="/api/recibos", tags=["recibos"])


def _service(request: Request) -> CuentaCorrienteService:
    return CuentaCorrienteService(request.app.state.conn)


class PagoCCPayload(BaseModel):
    """El formulario de pago del kit (`PagoCCPayload` del router del motor)."""

    monto: float
    fecha: str
    concepto: str = "Pago a cuenta"
    referencia: str = ""
    medio_pago: str = "efectivo"
    caja_id: int | None = None

    @field_validator("medio_pago")
    @classmethod
    def _medio_de_cobro(cls, medio: str) -> str:
        # 🔴 La cuenta corriente no es un medio de COBRO: es la marca de que
        # la operación se hizo a crédito (ver `CobranzaIn` en
        # `app/routers/accounts.py`).
        if medio == "cuenta_corriente":
            raise ValueError("la cuenta corriente no es un medio para cobrar una deuda")
        return medios_pago.validar(medio)


@router.get("")
def listar(request: Request):
    """Quiénes deben, con la deuda total para el cartel del kit."""
    return _service(request).listado_kit()


@router.get("/cajas")
def cajas_del_turno(user: dict = Depends(get_current_user)):
    """La caja del turno abierto de quien consulta, y sólo esa.

    El kit la usa para preseleccionar la caja del pago; en este producto el
    ingreso SIEMPRE cae en la caja del turno de quien cobra, así que ofrecer
    las demás sería ofrecer algo que el backend no honra. Sin turno abierto,
    lista vacía: el selector se oculta y el cobro va a chocar con el 409.
    """
    turno = db_turnos.get_turno_activo(int(user["id"])) if user else None
    if turno is None or not turno.get("caja_id"):
        return []
    return [c for c in db_caja.get_all_cajas() if c["id"] == turno["caja_id"]]


@router.get("/{party_id}")
def detalle(party_id: int, request: Request):
    try:
        return _service(request).detalle_kit(party_id)
    except SinCliente as exc:
        raise HTTPException(404, str(exc))


@router.post("/{party_id}/pagar")
def pagar(party_id: int, payload: PagoCCPayload, request: Request,
          user: dict = Depends(get_current_user)):
    """Registra un pago a cuenta desde el kit.

    Mismo negocio que `POST /accounts/{party_id}/payments`: exige turno
    abierto (409 si no) y el ingreso cae en la caja del turno. Lo que suma el
    kit: la fecha del pago y, si venía, la caja -- que acá tiene que ser la
    del turno (422 si no), porque es la única que el arqueo va a mirar.
    """
    turno = db_turnos.get_turno_activo(int(user["id"])) if user else None
    if turno is None:
        raise HTTPException(409, "no hay un turno de caja abierto")
    if payload.caja_id is not None and payload.caja_id != turno.get("caja_id"):
        raise HTTPException(422, "la cobranza cae en la caja del turno abierto")

    servicio = _service(request)
    try:
        cobranza = servicio.registrar_cobranza(
            party_id, Decimal(str(payload.monto)), payload.medio_pago,
            concepto=payload.concepto, referencia=payload.referencia,
            turno_id=turno["id"], usuario_id=int(user["id"]) if user else None,
            fecha=payload.fecha, caja_id=turno.get("caja_id"),
        )
    except SinCliente as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    return {
        "movimientos": servicio.movimientos(party_id),
        "saldo": float(servicio.saldo(party_id)),
        "recibo_id": cobranza.recibo_id,
    }


@router.delete("/pagos/{pago_id}", dependencies=[Depends(require_admin)])
def eliminar_pago(pago_id: int, request: Request,
                  user: dict = Depends(get_current_user)):
    """Baja de un pago a cuenta, admin-only (misma regla que el motor para
    Contalibra/Restolibra). Anula recibo y movimiento de caja, después borra
    el pago; ver `CuentaCorrienteService.eliminar_pago`."""
    try:
        _service(request).eliminar_pago(
            pago_id, usuario_id=int(user["id"]) if user else None)
    except SinPago as exc:
        raise HTTPException(404, str(exc))
    except SinMovimientoDeCaja as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@router_recibos.post("/cobranza/{cc_pago_id}")
def emitir_recibo_cobranza(cc_pago_id: int, user: dict = Depends(get_current_user)):
    """El recibo de un pago, idempotente: la ruta que llama el kit, misma
    operación que `POST /accounts/receipts/{cc_pago_id}`."""
    return {"id": accounts.emitir_recibo(cc_pago_id, user=user).id}


@router_recibos.get("/{recibo_id}/pdf")
def recibo_pdf(recibo_id: int, user: dict = Depends(get_current_user)):
    # Misma respuesta byte a byte que `GET /accounts/receipts/{recibo_id}/pdf`
    # (el navegador la pide por URL, con la cookie de sesión).
    return accounts.recibo_pdf(recibo_id, user=user)