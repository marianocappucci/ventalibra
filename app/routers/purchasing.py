from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..services.purchasing import (
    InvalidPurchaseState,
    PurchaseOrderNotFound,
    PurchaseReceiptNotFound,
    PurchasingService,
)

router = APIRouter(tags=["purchasing"])


class PurchaseOrderCreate(BaseModel):
    supplier_party_id: int
    branch_id: int | None = None


class PurchaseOrderItemCreate(BaseModel):
    item_id: int
    quantity_ordered: Decimal
    unit_cost: Decimal
    tax_rate: Decimal = Decimal("0")


class PurchaseOrderItemOut(BaseModel):
    item_id: int
    quantity_ordered: Decimal
    quantity_received: Decimal
    pending_quantity: Decimal
    unit_cost: Decimal
    tax_rate: Decimal
    subtotal: Decimal


class PurchaseOrderOut(BaseModel):
    id: int
    number: str
    supplier_party_id: int
    status: str
    items: list[PurchaseOrderItemOut]
    is_fully_received: bool


def _to_order_out(order) -> PurchaseOrderOut:
    return PurchaseOrderOut(
        id=order.id, number=order.number, supplier_party_id=order.supplier_party_id,
        status=order.status,
        items=[
            PurchaseOrderItemOut(
                item_id=item.item_id, quantity_ordered=item.quantity_ordered,
                quantity_received=item.quantity_received, pending_quantity=item.pending_quantity,
                unit_cost=item.unit_cost, tax_rate=item.tax_rate, subtotal=item.subtotal,
            )
            for item in order.items
        ],
        is_fully_received=order.is_fully_received(),
    )


class PurchaseReceiptCreate(BaseModel):
    supplier_party_id: int
    purchase_order_id: int | None = None
    document_reference: str | None = None


class PurchaseReceiptItemCreate(BaseModel):
    item_id: int
    quantity: Decimal
    unit_cost: Decimal
    lot_code: str | None = None
    expires_at: datetime | None = None


class PurchaseReceiptItemOut(BaseModel):
    item_id: int
    quantity: Decimal
    unit_cost: Decimal
    lot_code: str | None
    expires_at: str | None


class PurchaseReceiptOut(BaseModel):
    id: int
    supplier_party_id: int
    purchase_order_id: int | None
    status: str
    items: list[PurchaseReceiptItemOut]
    received_at: str | None
    document_reference: str | None


def _to_receipt_out(receipt) -> PurchaseReceiptOut:
    return PurchaseReceiptOut(
        id=receipt.id, supplier_party_id=receipt.supplier_party_id,
        purchase_order_id=receipt.purchase_order_id, status=receipt.status,
        items=[
            PurchaseReceiptItemOut(
                item_id=item.item_id, quantity=item.quantity, unit_cost=item.unit_cost,
                lot_code=item.lot_code,
                expires_at=item.expires_at.isoformat() if item.expires_at else None,
            )
            for item in receipt.items
        ],
        received_at=receipt.received_at.isoformat() if receipt.received_at else None,
        document_reference=receipt.document_reference,
    )


class ReceiptConfirm(BaseModel):
    location_id: int


def _service(request: Request) -> PurchasingService:
    return PurchasingService(request.app.state.conn)


@router.post("/purchase-orders", response_model=PurchaseOrderOut)
def create_order(data: PurchaseOrderCreate, request: Request):
    order = _service(request).create_order(
        supplier_party_id=data.supplier_party_id, branch_id=data.branch_id,
    )
    return _to_order_out(order)


@router.get("/purchase-orders/{order_id}", response_model=PurchaseOrderOut)
def get_order(order_id: int, request: Request):
    try:
        return _to_order_out(_service(request).get_order(order_id))
    except PurchaseOrderNotFound:
        raise HTTPException(404, "purchase order not found")


@router.post("/purchase-orders/{order_id}/items", response_model=PurchaseOrderOut)
def add_order_item(order_id: int, data: PurchaseOrderItemCreate, request: Request):
    try:
        order = _service(request).add_order_item(
            order_id, item_id=data.item_id, quantity_ordered=data.quantity_ordered,
            unit_cost=data.unit_cost, tax_rate=data.tax_rate,
        )
    except PurchaseOrderNotFound:
        raise HTTPException(404, "purchase order not found")
    except InvalidPurchaseState as exc:
        raise HTTPException(409, str(exc))
    return _to_order_out(order)


@router.post("/purchase-receipts", response_model=PurchaseReceiptOut)
def create_receipt(data: PurchaseReceiptCreate, request: Request):
    try:
        receipt = _service(request).create_receipt(
            supplier_party_id=data.supplier_party_id,
            purchase_order_id=data.purchase_order_id,
            document_reference=data.document_reference,
        )
    except PurchaseOrderNotFound:
        raise HTTPException(404, "purchase order not found")
    return _to_receipt_out(receipt)


@router.get("/purchase-receipts/{receipt_id}", response_model=PurchaseReceiptOut)
def get_receipt(receipt_id: int, request: Request):
    try:
        return _to_receipt_out(_service(request).get_receipt(receipt_id))
    except PurchaseReceiptNotFound:
        raise HTTPException(404, "purchase receipt not found")


@router.post("/purchase-receipts/{receipt_id}/items", response_model=PurchaseReceiptOut)
def add_receipt_item(receipt_id: int, data: PurchaseReceiptItemCreate, request: Request):
    try:
        receipt = _service(request).add_receipt_item(
            receipt_id, item_id=data.item_id, quantity=data.quantity,
            unit_cost=data.unit_cost, lot_code=data.lot_code, expires_at=data.expires_at,
        )
    except PurchaseReceiptNotFound:
        raise HTTPException(404, "purchase receipt not found")
    except InvalidPurchaseState as exc:
        raise HTTPException(409, str(exc))
    return _to_receipt_out(receipt)


@router.post("/purchase-receipts/{receipt_id}/confirm", response_model=PurchaseReceiptOut)
def confirm_receipt(receipt_id: int, data: ReceiptConfirm, request: Request):
    try:
        receipt = _service(request).confirm_receipt(receipt_id, location_id=data.location_id)
    except PurchaseReceiptNotFound:
        raise HTTPException(404, "purchase receipt not found")
    except InvalidPurchaseState as exc:
        raise HTTPException(409, str(exc))
    return _to_receipt_out(receipt)
