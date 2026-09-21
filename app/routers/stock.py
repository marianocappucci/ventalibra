from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import get_current_user, require_admin
from ..conexion import conexion_utilizable
from ..services.stock import (
    DepositoInexistente,
    StockService,
    TransferenciaInvalida,
)

router = APIRouter(prefix="/stock", tags=["stock"])


class AdjustmentCreate(BaseModel):
    item_id: int
    location_id: int
    quantity_delta: Decimal
    reason: str = ""
    variant_id: int | None = None


class TransferenciaIn(BaseModel):
    item_id: int
    origen_id: int
    destino_id: int
    cantidad: Decimal
    nota: str = ""
    variant_id: int | None = None


class CurrentStockOut(BaseModel):
    item_id: int
    location_id: int
    variant_id: int | None
    quantity: Decimal


def _service(request: Request) -> StockService:
    return StockService(request.app.state.conn)


@router.post("/adjustments")
def create_adjustment(data: AdjustmentCreate, request: Request):
    _service(request).adjust(
        data.item_id, data.location_id, data.quantity_delta, data.reason, variant_id=data.variant_id
    )
    return {"ok": True}


@router.get("/{item_id}", response_model=CurrentStockOut)
def current_stock(item_id: int, location_id: int, request: Request, variant_id: int | None = None):
    quantity = _service(request).current_stock(item_id, location_id, variant_id=variant_id)
    return CurrentStockOut(item_id=item_id, location_id=location_id, variant_id=variant_id, quantity=quantity)


# ── Transferencia entre sucursales ───────────────────────────────────────
#
# Sólo admin, igual que el alta y la edición de sucursales y de cajas
# (`routers/locations.py`, `routers/cajas.py`): mover mercadería entre locales
# cambia el stock de dos lados a la vez y no es una operación de mostrador.


@router.post("/transferir", dependencies=[Depends(require_admin)])
def transferir(data: TransferenciaIn, request: Request,
               user: dict = Depends(get_current_user)):
    """Mueve stock de una sucursal o depósito a otro, en una transacción.

    Devuelve el stock que quedó de los dos lados, para que la pantalla lo
    pinte sin volver a preguntar.
    """
    try:
        with conexion_utilizable(request.app.state.conn):
            return _service(request).transferir(
                data.item_id, data.origen_id, data.destino_id, data.cantidad,
                nota=data.nota,
                usuario_id=int(user["id"]) if user else None,
                variant_id=data.variant_id,
            )
    except DepositoInexistente as e:
        raise HTTPException(404, str(e)) from e
    except TransferenciaInvalida as e:
        raise HTTPException(422, str(e)) from e


@router.get("/transferencias/historial")
def listar_transferencias(request: Request, location_id: int | None = None, limit: int = 200):
    """El historial de transferencias, reconstruido desde el ledger.

    ⚠️ La ruta dice `/transferencias/historial` y no `/transferencias` porque
    `GET /stock/{item_id}` ya existe y captura cualquier segmento suelto: sin
    el segundo tramo, `/stock/transferencias` entraría por ahí con
    `item_id="transferencias"` y daría un 422 de validación en vez de esta
    lista. Lo mismo vale para cualquier GET que se agregue después.
    """
    return _service(request).transferencias(location_id=location_id, limit=limit)
