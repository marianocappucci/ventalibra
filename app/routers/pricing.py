import sqlite3
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..services.pricing import PricingService

router = APIRouter(prefix="/pricing", tags=["pricing"])


class PriceListCreate(BaseModel):
    name: str
    description: str = ""
    is_default: bool = False


class PriceListOut(BaseModel):
    id: int
    name: str
    description: str
    active: bool
    is_default: bool


def _to_price_list_out(price_list) -> PriceListOut:
    return PriceListOut(
        id=price_list.id, name=price_list.name, description=price_list.description,
        active=price_list.active, is_default=price_list.is_default,
    )


class ItemPriceCreate(BaseModel):
    price_list_id: int
    amount: Decimal
    valid_from: datetime
    valid_until: datetime | None = None
    min_quantity: Decimal | None = None
    branch_id: int | None = None


class ItemPriceOut(BaseModel):
    id: int
    item_id: int
    price_list_id: int
    amount: Decimal
    currency: str
    valid_from: datetime
    valid_until: datetime | None
    min_quantity: Decimal | None
    branch_id: int | None


def _to_item_price_out(item_price) -> ItemPriceOut:
    return ItemPriceOut(
        id=item_price.id, item_id=item_price.item_id, price_list_id=item_price.price_list_id,
        amount=item_price.amount, currency=item_price.currency, valid_from=item_price.valid_from,
        valid_until=item_price.valid_until, min_quantity=item_price.min_quantity,
        branch_id=item_price.branch_id,
    )


class ResolvedPriceOut(BaseModel):
    item_id: int
    amount: Decimal | None


def _service(request: Request) -> PricingService:
    return PricingService(request.app.state.conn)


@router.post("/lists", response_model=PriceListOut)
def create_price_list(data: PriceListCreate, request: Request):
    try:
        price_list = _service(request).create_price_list(data.name, data.description, data.is_default)
    except sqlite3.IntegrityError as exc:
        # Indice parcial unico: como mucho una lista default.
        raise HTTPException(409, str(exc))
    return _to_price_list_out(price_list)


@router.get("/lists/{price_list_id}", response_model=PriceListOut)
def get_price_list(price_list_id: int, request: Request):
    price_list = _service(request).get_price_list(price_list_id)
    if price_list is None:
        raise HTTPException(404, "price list not found")
    return _to_price_list_out(price_list)


@router.post("/items/{item_id}/prices", response_model=ItemPriceOut)
def set_item_price(item_id: int, data: ItemPriceCreate, request: Request):
    try:
        item_price = _service(request).set_item_price(
            item_id, data.price_list_id, data.amount, valid_from=data.valid_from,
            valid_until=data.valid_until, min_quantity=data.min_quantity, branch_id=data.branch_id,
        )
    except ValueError as exc:
        # valid_until <= valid_from -- invariante del dominio.
        raise HTTPException(422, str(exc))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(422, str(exc))
    return _to_item_price_out(item_price)


@router.get("/items/{item_id}/prices", response_model=list[ItemPriceOut])
def list_item_prices(item_id: int, request: Request):
    return [_to_item_price_out(p) for p in _service(request).list_item_prices(item_id)]


@router.get("/items/{item_id}/resolve", response_model=ResolvedPriceOut)
def resolve_price(
    item_id: int, request: Request,
    price_list_id: int | None = None, quantity: Decimal = Decimal("1"), branch_id: int | None = None,
):
    amount = _service(request).resolve_price(
        item_id, price_list_id=price_list_id, quantity=quantity, branch_id=branch_id
    )
    return ResolvedPriceOut(item_id=item_id, amount=amount)
