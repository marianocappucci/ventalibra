import sqlite3
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from libracommerce.domain.catalog import CatalogItemType, ItemCodeType

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


class ItemCodeCreate(BaseModel):
    code_type: str
    code: str
    is_primary: bool = False


class ItemCodeOut(BaseModel):
    id: int
    item_id: int
    code_type: str
    code: str
    is_primary: bool


def _to_code_out(item_code) -> ItemCodeOut:
    return ItemCodeOut(
        id=item_code.id, item_id=item_code.item_id, code_type=item_code.code_type,
        code=item_code.code, is_primary=item_code.is_primary,
    )


class ItemVariantCreate(BaseModel):
    sku: str
    name: str
    attributes: dict[str, str] = {}


class ItemVariantOut(BaseModel):
    id: int
    item_id: int
    sku: str
    name: str
    attributes: dict[str, str]
    active: bool


def _to_variant_out(variant) -> ItemVariantOut:
    return ItemVariantOut(
        id=variant.id, item_id=variant.item_id, sku=variant.sku,
        name=variant.name, attributes=variant.attributes, active=variant.active,
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


@router.get("/items/scan", response_model=ItemOut)
def scan_item(code: str, request: Request):
    # Ruta literal "/items/scan" registrada ANTES de "/items/{item_id}" a
    # proposito: FastAPI/Starlette matchea rutas en orden de registro, y
    # ambas tienen la misma forma (dos segmentos) -- si "/items/{item_id}"
    # fuera primero, "scan" caeria ahi y fallaria al intentar convertirlo
    # a int en vez de llegar a este endpoint.
    item = _service(request).find_by_code(code)
    if item is None:
        raise HTTPException(404, "no item matches that code")
    return _to_item_out(item)


@router.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int, request: Request):
    item = _service(request).get_item(item_id)
    if item is None:
        raise HTTPException(404, "item not found")
    return _to_item_out(item)


@router.post("/items/{item_id}/codes", response_model=ItemCodeOut)
def add_code(item_id: int, data: ItemCodeCreate, request: Request):
    try:
        code_type = ItemCodeType(data.code_type)
    except ValueError:
        raise HTTPException(422, f"invalid code_type: {data.code_type!r}")
    try:
        item_code = _service(request).add_code(item_id, code_type, data.code, is_primary=data.is_primary)
    except sqlite3.IntegrityError as exc:
        # UNIQUE(code_type, code) o el indice parcial de un solo primario
        # por item -- ambos son errores de datos del cliente, no del server.
        raise HTTPException(409, str(exc))
    return _to_code_out(item_code)


@router.get("/items/{item_id}/codes", response_model=list[ItemCodeOut])
def list_codes(item_id: int, request: Request):
    return [_to_code_out(c) for c in _service(request).list_codes(item_id)]


@router.post("/items/{item_id}/variants", response_model=ItemVariantOut)
def add_variant(item_id: int, data: ItemVariantCreate, request: Request):
    try:
        variant = _service(request).add_variant(item_id, data.sku, data.name, attributes=data.attributes)
    except sqlite3.IntegrityError as exc:
        # UNIQUE(sku) -- error de datos del cliente, no del server.
        raise HTTPException(409, str(exc))
    return _to_variant_out(variant)


@router.get("/items/{item_id}/variants", response_model=list[ItemVariantOut])
def list_variants(item_id: int, request: Request):
    return [_to_variant_out(v) for v in _service(request).list_variants(item_id)]
