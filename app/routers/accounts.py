"""Cuenta corriente de clientes: saldo, movimientos y cobranzas.

Fiar ocurre al confirmar la venta (ver `routers/sales.py`); acá está el otro
lado: cuánto debe cada uno y el registro del pago cuando viene a saldar.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from libracore.db import turnos as db_turnos

from ..auth import get_current_user
from ..services.cuenta_corriente import CuentaCorrienteService, SinCliente

router = APIRouter(prefix="/accounts", tags=["accounts"])


class CobranzaIn(BaseModel):
    monto: Decimal
    medio_pago: str = "efectivo"
    concepto: str = ""
    referencia: str = ""


class MovimientoOut(BaseModel):
    fecha: str
    tipo: str
    concepto: str
    monto: Decimal
    medio: str = ""
    referencia: str = ""


class CuentaOut(BaseModel):
    party_id: int
    saldo: Decimal
    movimientos: list[MovimientoOut]


class DeudorOut(BaseModel):
    party_id: int
    nombre: str
    saldo: Decimal


def _service(request: Request) -> CuentaCorrienteService:
    return CuentaCorrienteService(request.app.state.conn)


@router.get("", response_model=list[DeudorOut])
def listar_deudores(request: Request):
    """Quiénes tienen cuenta corriente abierta y por cuánto."""
    return [DeudorOut(**d) for d in _service(request).deudores()]


@router.get("/{party_id}", response_model=CuentaOut)
def ver_cuenta(party_id: int, request: Request):
    servicio = _service(request)
    try:
        saldo = servicio.saldo(party_id)
        movimientos = servicio.movimientos(party_id)
    except SinCliente as exc:
        raise HTTPException(404, str(exc))
    return CuentaOut(
        party_id=party_id,
        saldo=saldo,
        movimientos=[
            MovimientoOut(
                fecha=m["fecha"], tipo=m["tipo"], concepto=m["concepto"],
                monto=Decimal(str(m["monto"])), medio=m.get("medio") or "",
                referencia=m.get("referencia") or "",
            )
            for m in movimientos
        ],
    )


@router.post("/{party_id}/payments", response_model=CuentaOut)
def cobrar(party_id: int, data: CobranzaIn, request: Request,
           user: dict = Depends(get_current_user)):
    """Registra un pago de deuda vieja.

    A diferencia de fiar, esto SÍ es plata que entra: exige turno abierto y
    genera movimiento de caja, para que el arqueo del cierre lo cuente.
    """
    turno = db_turnos.get_turno_activo_any()
    if turno is None:
        raise HTTPException(409, "no hay un turno de caja abierto")

    servicio = _service(request)
    try:
        servicio.registrar_cobranza(
            party_id, data.monto, data.medio_pago,
            concepto=data.concepto, referencia=data.referencia,
            turno_id=turno["id"], usuario_id=int(user["id"]) if user else None,
        )
    except SinCliente as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    return ver_cuenta(party_id, request)
