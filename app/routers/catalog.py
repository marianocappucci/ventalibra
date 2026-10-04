"""Administración de **unidades** y **categorías** del catálogo (Configuración).

Desde la fase 7 (2026-09-27, ADR-034) los productos —alta, edición, códigos, variantes y escaneo— son el router del
motor (`/api/productos`, `app/productos_ganchos.py`). Queda acá lo que el motor no tiene: las unidades con su código,
su nombre, si admiten fracciones y su escala decimal, y las categorías jerárquicas con baja lógica y nombre único entre
las activas.
"""
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from libracommerce.web._validacion import sin_booleanos
from pydantic import BaseModel

from ..services.catalog import CatalogService, CategoryInvalido, CategoryNotFound

router = APIRouter(prefix="/catalog", tags=["catalog"])


class CategoryCreate(BaseModel):
    name: str
    parent_id: int | None = None
    # `true` no es el padre 1 (ADR-028 del motor): sin esto pydantic lo convierte en 1 antes de que nadie lo mire.
    _no_son_booleanos = sin_booleanos("parent_id")


class CategoryUpdate(BaseModel):
    """`parent_id` no se edita -- ver el docstring de
    `CatalogService.update_category`."""

    name: str
    active: bool = True


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
    _no_son_booleanos = sin_booleanos("decimal_scale")


class UnitOut(BaseModel):
    code: str
    name: str
    allows_fraction: bool
    decimal_scale: int


def _service(request: Request) -> CatalogService:
    return CatalogService(request.app.state.conn)


@router.post("/categories", response_model=CategoryOut)
def create_category(data: CategoryCreate, request: Request):
    try:
        category = _service(request).create_category(data.name, data.parent_id)
    except CategoryInvalido as exc:
        # nombre vacio o repetido entre categorias activas -- ver
        # _validar_category_name.
        raise HTTPException(422, str(exc))
    return CategoryOut(id=category.id, name=category.name, parent_id=category.parent_id, active=category.active)


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, data: CategoryUpdate, request: Request):
    try:
        category = _service(request).update_category(category_id, name=data.name, active=data.active)
    except CategoryNotFound:
        raise HTTPException(404, "category not found")
    except CategoryInvalido as exc:
        # mismo criterio que create_category.
        raise HTTPException(422, str(exc))
    return CategoryOut(id=category.id, name=category.name, parent_id=category.parent_id, active=category.active)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(request: Request):
    return [
        CategoryOut(id=c.id, name=c.name, parent_id=c.parent_id, active=c.active)
        for c in _service(request).list_categories()
    ]


@router.post("/units", response_model=UnitOut)
def create_unit(data: UnitCreate, request: Request):
    try:
        unit = _service(request).create_unit(data.code, data.name, data.allows_fraction, data.decimal_scale)
    except sqlite3.IntegrityError:
        # UNIQUE(code). A diferencia de los otros 409 de este router el
        # mensaje no es el de sqlite: "units.code" no le dice nada a quien
        # esta cargando unidades desde la pantalla de catalogo.
        raise HTTPException(409, f"ya existe una unidad con el codigo {data.code!r}")
    return UnitOut(**unit.__dict__)


@router.get("/units", response_model=list[UnitOut])
def list_units(request: Request):
    return [UnitOut(**u.__dict__) for u in _service(request).list_units()]
