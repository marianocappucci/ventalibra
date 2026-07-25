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


def _service(request: Request) -> LocationService:
    return LocationService(request.app.state.conn)


@router.post("", response_model=LocationOut)
def create_location(data: LocationCreate, request: Request):
    location = _service(request).create(data.name, data.location_type, data.branch_id)
    return LocationOut(**location.__dict__)


@router.get("", response_model=list[LocationOut])
def list_locations(request: Request):
    return [LocationOut(**loc.__dict__) for loc in _service(request).list()]
