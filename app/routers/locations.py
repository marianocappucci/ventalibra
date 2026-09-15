from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..services.locations import LocationService

router = APIRouter(prefix="/locations", tags=["locations"])


class LocationCreate(BaseModel):
    name: str
    location_type: str = "warehouse"
    branch_id: int | None = None


class LocationOut(BaseModel):
    id: int
    name: str
    branch_id: int | None
    location_type: str
    active: bool
    #: 🔴 Agregado 2026-09-14 (F3, ADR-025): el dominio (`Location.is_default`)
    #: ya lo traía -- `LocationOut(**location.__dict__)` lo venía DESCARTANDO
    #: en silencio (Pydantic ignora claves de más). Hace falta desde F3 porque
    #: `POST /api/ventas` ya no recibe `location_id`: descuenta siempre del
    #: default (`erp.stock.descontar_stock_venta`), y sin este campo no hay
    #: forma de que un cliente HTTP (la SPA, `scripts/seed_demo.py`) sepa CUÁL
    #: de los depósitos es ese -- antes no hacía falta saberlo, porque
    #: `/sales/{id}/confirm` dejaba elegir cualquiera.
    is_default: bool


def _service(request: Request) -> LocationService:
    return LocationService(request.app.state.conn)


@router.post("", response_model=LocationOut)
def create_location(data: LocationCreate, request: Request):
    location = _service(request).create(data.name, data.location_type, data.branch_id)
    return LocationOut(**location.__dict__)


@router.get("", response_model=list[LocationOut])
def list_locations(request: Request):
    return [LocationOut(**loc.__dict__) for loc in _service(request).list()]
