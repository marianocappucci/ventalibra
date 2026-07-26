from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..modules_gate import get_module_repository
from ..services import billing
from ..services.customers import CustomerService
from ..services.sales import InvalidSaleState, SaleNotFound, SaleService

router = APIRouter(prefix="/sales", tags=["sales"])


class SaleCreate(BaseModel):
    branch_id: int | None = None
    register_id: int | None = None
    customer_party_id: int | None = None


class SaleItemCreate(BaseModel):
    item_id: int
    quantity: Decimal
    unit_price: Decimal | None = None
    discount_amount: Decimal = Decimal("0")


class SaleConfirm(BaseModel):
    location_id: int
    medio_pago: str
    invoice: bool = False


class SaleItemOut(BaseModel):
    kind: str
    item_id: int | None
    description_snapshot: str
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    line_total: Decimal


class SaleOut(BaseModel):
    id: int
    number: str
    status: str
    items: list[SaleItemOut]
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal
    confirmed_at: str | None
    factura: dict | None = None


def _to_sale_out(sale) -> SaleOut:
    return SaleOut(
        id=sale.id, number=sale.number, status=sale.status,
        items=[
            SaleItemOut(
                kind=item.kind, item_id=item.item_id,
                description_snapshot=item.description_snapshot,
                quantity=item.quantity, unit_price=item.unit_price,
                discount_amount=item.discount_amount, tax_amount=item.tax_amount,
                line_total=item.line_total,
            )
            for item in sale.items
        ],
        subtotal=sale.subtotal, discount_total=sale.discount_total,
        tax_total=sale.tax_total, total=sale.total,
        confirmed_at=sale.confirmed_at.isoformat() if sale.confirmed_at else None,
    )


def _service(request: Request) -> SaleService:
    return SaleService(request.app.state.conn)


@router.post("", response_model=SaleOut)
def create_sale(data: SaleCreate, request: Request):
    sale = _service(request).create_draft(
        branch_id=data.branch_id, register_id=data.register_id,
        customer_party_id=data.customer_party_id,
    )
    return _to_sale_out(sale)


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: int, request: Request):
    try:
        return _to_sale_out(_service(request).get(sale_id))
    except SaleNotFound:
        raise HTTPException(404, "sale not found")


@router.post("/{sale_id}/items", response_model=SaleOut)
def add_item(sale_id: int, data: SaleItemCreate, request: Request):
    try:
        sale = _service(request).add_item(
            sale_id, item_id=data.item_id, quantity=data.quantity,
            unit_price=data.unit_price, discount_amount=data.discount_amount,
        )
    except SaleNotFound:
        raise HTTPException(404, "sale not found")
    except InvalidSaleState as exc:
        raise HTTPException(409, str(exc))
    except KeyError as exc:
        raise HTTPException(422, str(exc))
    return _to_sale_out(sale)


@router.post("/{sale_id}/confirm", response_model=SaleOut)
async def confirm_sale(sale_id: int, data: SaleConfirm, request: Request):
    # El gating por plan corre aca adentro, no gateando todo el router:
    # confirmar una venta (y su movimiento de caja, siempre) nunca depende
    # del plan -- solo pedir factura sobre esa venta puntual lo hace.
    # Mismo criterio que gestiolibra/medlibra (ver DECISIONS.md ADR-0XX de
    # este repo): el bloqueo tiene que fallar antes de tocar nada, no a
    # mitad de camino.
    if data.invoice and not get_module_repository(request).is_enabled("facturacion"):
        raise HTTPException(403, "modulo 'facturacion' no incluido en el plan actual")

    try:
        sale = _service(request).confirm(sale_id, location_id=data.location_id)
    except SaleNotFound:
        raise HTTPException(404, "sale not found")
    except InvalidSaleState as exc:
        raise HTTPException(409, str(exc))

    referencia = f"sale-{sale.id}"
    factura = None
    if data.invoice:
        customer_billing = None
        if sale.customer_party_id is not None:
            customer_billing = CustomerService(request.app.state.conn).get_billing(sale.customer_party_id)
        factura = await billing.invoice_sale(customer_billing, sale, referencia)

    # Caja siempre se registra al confirmar una venta cobrada, factures o
    # no -- decision explicita del usuario (ver DECISIONS.md ADR-007):
    # el control de caja es independiente del tema fiscal.
    billing.record_sale_payment(
        sale, data.medio_pago, referencia, factura_id=factura["id"] if factura else None,
    )

    out = _to_sale_out(sale)
    out.factura = factura
    return out
