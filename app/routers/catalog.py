from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from libracommerce.domain.catalog import CatalogItemType

from ..services.catalog import CatalogService

router = APIRouter(prefix="/catalog", tags=["catalog"])


class CategoryCreate(BaseModel):
    name: str
    parent_id: int | None = None


class CategoryOut(BaseModel):
    id: int
    name: str
    parent_id: int | None
    active: bool


class UnitCreate(BaseModel):
    code: str
    name: str
    allows_fraction: bool = False
    decimal_scale: int = 0


class UnitOut(BaseModel):
    code: str
    name: str
    allows_fraction: bool
    decimal_scale: int


class ItemCreate(BaseModel):
    name: str
    unit_code: str
    item_type: str = "product"
    category_id: int | None = None
    description: str = ""
    default_sale_price: Decimal = Decimal("0")
    default_cost: Decimal = Decimal("0")


class ItemOut(BaseModel):
    id: int
    item_type: str
    name: str
    description: str
    category_id: int | None
    unit_code: str
    active: bool
    sellable: bool
    purchasable: bool
    default_sale_price: Decimal
    default_cost: Decimal


def _to_item_out(item) -> ItemOut:
    return ItemOut(
        id=item.id, item_type=item.item_type, name=item.name, description=item.description,
        category_id=item.category_id, unit_code=item.unit.code, active=item.active,
        sellable=item.sellable, purchasable=item.purchasable,
        default_sale_price=item.default_sale_price, default_cost=item.default_cost,
    )


def _service(request: Request) -> CatalogService:
    return CatalogService(request.app.state.conn)


@router.post("/categories", response_model=CategoryOut)
def create_category(data: CategoryCreate, request: Request):
    category = _service(request).create_category(data.name, data.parent_id)
    return CategoryOut(id=category.id, name=category.name, parent_id=category.parent_id, active=category.active)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(request: Request):
    return [
        CategoryOut(id=c.id, name=c.name, parent_id=c.parent_id, active=c.active)
        for c in _service(request).list_categories()
    ]


@router.post("/units", response_model=UnitOut)
def create_unit(data: UnitCreate, request: Request):
    unit = _service(request).create_unit(data.code, data.name, data.allows_fraction, data.decimal_scale)
    return UnitOut(**unit.__dict__)


@router.get("/units", response_model=list[UnitOut])
def list_units(request: Request):
    return [UnitOut(**u.__dict__) for u in _service(request).list_units()]


@router.post("/items", response_model=ItemOut)
def create_item(data: ItemCreate, request: Request):
    try:
        item_type = CatalogItemType(data.item_type)
    except ValueError:
        raise HTTPException(422, f"invalid item_type: {data.item_type!r}")
    try:
        item = _service(request).create_item(
            name=data.name, unit_code=data.unit_code, item_type=item_type,
            category_id=data.category_id, description=data.description,
            default_sale_price=data.default_sale_price, default_cost=data.default_cost,
        )
    except KeyError as exc:
        raise HTTPException(422, str(exc))
    return _to_item_out(item)


@router.get("/items", response_model=list[ItemOut])
def list_items(request: Request, category_id: int | None = None, search: str | None = None):
    items = _service(request).list_items(category_id=category_id, search=search)
    return [_to_item_out(item) for item in items]


@router.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int, request: Request):
    item = _service(request).get_item(item_id)
    if item is None:
        raise HTTPException(404, "item not found")
    return _to_item_out(item)
