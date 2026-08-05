"""Cuenta corriente de clientes: saldo, movimientos y cobranzas.

Fiar ocurre al confirmar la venta (ver `routers/sales.py`); acá está el otro
lado: cuánto debe cada uno y el registro del pago cuando viene a saldar.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from libracore.db import recibos as db_recibos
from libracore.db import turnos as db_turnos
from libracore.pdf_generator import generate_pdf_recibo_doc
from libracore.recibos import SinCobros, emitir_recibo_cobranza

from ..auth import get_current_user
from ..services.cuenta_corriente import CuentaCorrienteService, SinCliente

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _numero_visible(recibo: dict) -> str:
    return f"{str(recibo['punto_venta']).zfill(4)}-{str(recibo['numero']).zfill(8)}"


def _recibo_out(recibo: dict) -> "ReciboOut":
    return ReciboOut(
        id=recibo["id"],
        numero_visible=_numero_visible(recibo),
        fecha=recibo["fecha"],
        cliente_razon=recibo["cliente_razon"],
        concepto=recibo["concepto"],
        total=Decimal(str(recibo["total"])),
        anulado=recibo["anulado"],
    )


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
    #: Sólo los abonos lo tienen. Es lo que le permite a la pantalla ofrecer
    #: el recibo de ese pago y no de los cargos, que no son plata que entró.
    cc_pago_id: int | None = None


class CuentaOut(BaseModel):
    party_id: int
    saldo: Decimal
    movimientos: list[MovimientoOut]
    #: Sólo viene poblado en la respuesta de un cobro recién hecho, para que
    #: la pantalla abra el recibo sola. Ver `registrar_cobranza`.
    recibo_id: int | None = None


class ReciboOut(BaseModel):
    id: int
    numero_visible: str
    fecha: str
    cliente_razon: str
    concepto: str
    total: Decimal
    anulado: bool


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
def ver_cuenta(party_id: int, request: Request, recibo_id: int | None = None):
    servicio = _service(request)
    try:
        saldo = servicio.saldo(party_id)
        movimientos = servicio.movimientos(party_id)
    except SinCliente as exc:
        raise HTTPException(404, str(exc))
    return CuentaOut(
        party_id=party_id,
        saldo=saldo,
        recibo_id=recibo_id,
        movimientos=[
            MovimientoOut(
                fecha=m["fecha"], tipo=m["tipo"], concepto=m["concepto"],
                monto=Decimal(str(m["monto"])), medio=m.get("medio") or "",
                referencia=m.get("referencia") or "",
                cc_pago_id=m.get("cc_pago_id"),
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
        cobranza = servicio.registrar_cobranza(
            party_id, data.monto, data.medio_pago,
            concepto=data.concepto, referencia=data.referencia,
            turno_id=turno["id"], usuario_id=int(user["id"]) if user else None,
        )
    except SinCliente as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    return ver_cuenta(party_id, request, recibo_id=cobranza.recibo_id)


# ── Recibos ──────────────────────────────────────────────────────────────────
# El comprobante del cobro (libracore >= v1.9.0). Viven acá y no en un router
# propio porque en VentaLibra el único origen es la cobranza de cuenta
# corriente: la venta de mostrador se lleva su ticket termico, no un recibo A4.


@router.post("/receipts/{cc_pago_id}", response_model=ReciboOut)
def emitir_recibo(cc_pago_id: int, user: dict = Depends(get_current_user)):
    """Emite el recibo de un pago, o devuelve el que ya tenia.

    Es idempotente, asi que la pantalla lo puede llamar sin saber si existe —
    por eso alcanza un solo boton.
    """
    try:
        recibo = emitir_recibo_cobranza(
            cc_pago_id, usuario_id=int(user["id"]) if user else None)
    except SinCobros as exc:
        raise HTTPException(404, str(exc))
    return _recibo_out(recibo)


@router.get("/receipts/{recibo_id}/pdf")
def recibo_pdf(recibo_id: int, user: dict = Depends(get_current_user)):
    recibo = db_recibos.get_recibo(recibo_id)
    if not recibo:
        raise HTTPException(404, "recibo no encontrado")
    return Response(
        content=generate_pdf_recibo_doc(recibo),
        media_type="application/pdf",
        headers={"Content-Disposition":
                 f'inline; filename="recibo_{_numero_visible(recibo)}.pdf"'},
    )
