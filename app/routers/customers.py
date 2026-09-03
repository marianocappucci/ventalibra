from fastapi import APIRouter, HTTPException, Request
from libracommerce.domain.entities import PartyType
from pydantic import BaseModel

from ..services.customers import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"])


class CustomerCreate(BaseModel):
    display_name: str
    party_type: str = "person"
    email: str | None = None
    phone: str | None = None
    cuit: str | None = None
    condicion_iva: str | None = None


class CustomerOut(BaseModel):
    id: int
    party_type: str
    display_name: str
    email: str | None
    phone: str | None
    active: bool
    cuit: str | None
    condicion_iva: str | None


def _service(request: Request) -> CustomerService:
    return CustomerService(request.app.state.conn)


@router.post("", response_model=CustomerOut)
def create_customer(data: CustomerCreate, request: Request):
    try:
        party_type = PartyType(data.party_type)
    except ValueError:
        raise HTTPException(422, f"invalid party_type: {data.party_type!r}")
    customer = _service(request).create(
        display_name=data.display_name, party_type=party_type,
        email=data.email, phone=data.phone,
        cuit=data.cuit, condicion_iva=data.condicion_iva,
    )
    return CustomerOut(**customer)


@router.get("", response_model=list[CustomerOut])
def list_customers(request: Request):
    return [CustomerOut(**c) for c in _service(request).list_all()]


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, request: Request):
    customer = _service(request).get(customer_id)
    if customer is None:
        raise HTTPException(404, "customer not found")
    return CustomerOut(**customer)
