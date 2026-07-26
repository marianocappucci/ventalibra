from decimal import Decimal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..services.stock import StockService

router = APIRouter(prefix="/stock", tags=["stock"])


class AdjustmentCreate(BaseModel):
    item_id: int
    location_id: int
    quantity_delta: Decimal
    reason: str = ""
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
