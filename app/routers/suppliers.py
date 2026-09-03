from fastapi import APIRouter, HTTPException, Request
from libracommerce.domain.entities import PartyType
from pydantic import BaseModel

from ..services.suppliers import SupplierService

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


class SupplierCreate(BaseModel):
    display_name: str
    party_type: str = "organization"
    legal_name: str | None = None
    tax_id: str | None = None
    email: str | None = None
    phone: str | None = None


class SupplierOut(BaseModel):
    id: int
    party_type: str
    display_name: str
    legal_name: str | None
    tax_id: str | None
    email: str | None
    phone: str | None
    active: bool


def _to_supplier_out(party) -> SupplierOut:
    return SupplierOut(
        id=party.id, party_type=party.party_type, display_name=party.display_name,
        legal_name=party.legal_name, tax_id=party.tax_id, email=party.email,
        phone=party.phone, active=party.active,
    )


def _service(request: Request) -> SupplierService:
    return SupplierService(request.app.state.conn)


@router.post("", response_model=SupplierOut)
def create_supplier(data: SupplierCreate, request: Request):
    try:
        party_type = PartyType(data.party_type)
    except ValueError:
        raise HTTPException(422, f"invalid party_type: {data.party_type!r}")
    supplier = _service(request).create(
        display_name=data.display_name, party_type=party_type,
        legal_name=data.legal_name, tax_id=data.tax_id,
        email=data.email, phone=data.phone,
    )
    return _to_supplier_out(supplier)


@router.get("", response_model=list[SupplierOut])
def list_suppliers(request: Request):
    return [_to_supplier_out(party) for party in _service(request).list_all()]


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: int, request: Request):
    supplier = _service(request).get(supplier_id)
    if supplier is None:
        raise HTTPException(404, "supplier not found")
    return _to_supplier_out(supplier)
