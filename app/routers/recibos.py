"""Los recibos de cobranza que llama el kit (`/api/recibos`).

Las pantallas de cuenta corriente del kit piden estas dos rutas fijas: emitir el recibo de un pago
(idempotente) y bajar su PDF. **Código propio por ahora**: en Contalibra y Restolibra el router de recibos
también es de cada producto (`app/web/api/recibos.py`), sin factory en el motor; extraerlo a `libracore`
es la deuda que cierra esto.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from libracore.db import recibos as db_recibos
from libracore.pdf_generator import generate_pdf_recibo_doc
from libracore.recibos import SinCobros, emitir_recibo_cobranza

from ..auth import get_current_user

router = APIRouter(prefix="/api/recibos", tags=["recibos"])


def _numero_visible(recibo: dict) -> str:
    return f"{str(recibo['punto_venta']).zfill(4)}-{str(recibo['numero']).zfill(8)}"


@router.post("/cobranza/{cc_pago_id}")
def emitir_recibo(cc_pago_id: int, user: dict = Depends(get_current_user)):
    """El recibo de un pago, o el que ya tenía: idempotente, la pantalla lo puede llamar sin saber si existe."""
    try:
        recibo = emitir_recibo_cobranza(cc_pago_id, usuario_id=int(user["id"]) if user else None)
    except SinCobros as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"id": recibo["id"]}


@router.get("/{recibo_id}/pdf")
def recibo_pdf(recibo_id: int, user: dict = Depends(get_current_user)):  # noqa: ARG001
    recibo = db_recibos.get_recibo(recibo_id)
    if not recibo:
        raise HTTPException(404, "recibo no encontrado")
    return Response(
        content=generate_pdf_recibo_doc(recibo),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="recibo_{_numero_visible(recibo)}.pdf"'},
    )
