"""Fase 2 -- Compras: PurchaseOrder/PurchaseReceipt ya modelados en
LibraCommerce (libracommerce/domain/purchasing.py).

Confirmar una recepcion delega enteramente en
libracommerce.usecases.purchasing.confirm_purchase_receipt (v0.1.2):
movimiento de stock por linea, actualizacion de CatalogItem.default_cost
(last-cost) y, si la recepcion esta vinculada a una orden, sincronizacion
de quantity_received/estado de esa orden. VentaLibra no reimplementa esa
orquestacion (a diferencia de las ventas en la Fase 1, que la reimplemento
porque LibraCommerce todavia no la ofrecia -- ver app/services/sales.py).
"""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from ..commerce import repositorio
from libracommerce.domain.purchasing import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderStatus,
    PurchaseReceipt,
    PurchaseReceiptItem,
    PurchaseReceiptStatus,
)
from libracommerce.usecases.purchasing import confirm_purchase_receipt

from ..db import next_sequence
from libracore.db.core import Conexion


class PurchaseOrderNotFound(Exception):
    pass


class PurchaseReceiptNotFound(Exception):
    pass


class InvalidPurchaseState(Exception):
    pass


class PurchasingService:
    def __init__(self, conn: Conexion):
        self._conn = conn
        self._repo = repositorio(conn)

    # ordenes de compra

    def create_order(self, *, supplier_party_id: int, branch_id: int | None = None) -> PurchaseOrder:
        number = f"OC-{next_sequence(self._conn, 'ventalibra_purchase_order'):06d}"
        order = PurchaseOrder(
            id=None, number=number, supplier_party_id=supplier_party_id,
            items=(), branch_id=branch_id,
        )
        return self._repo.save_purchase_order(order)

    def get_order(self, order_id: int) -> PurchaseOrder:
        order = self._repo.get_purchase_order(order_id)
        if order is None:
            raise PurchaseOrderNotFound(order_id)
        return order

    def list_orders(self) -> list[PurchaseOrder]:
        return list(self._repo.list_purchase_orders())

    def add_order_item(
        self, order_id: int, *, item_id: int, quantity_ordered: Decimal,
        unit_cost: Decimal, tax_rate: Decimal = Decimal("0"),
    ) -> PurchaseOrder:
        order = self.get_order(order_id)
        if order.status not in (PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.SENT):
            raise InvalidPurchaseState(
                f"la orden {order_id} no admite nuevas lineas (status={order.status})"
            )
        line = PurchaseOrderItem(
            item_id=item_id, quantity_ordered=quantity_ordered,
            unit_cost=unit_cost, tax_rate=tax_rate,
        )
        updated = replace(order, items=order.items + (line,))
        return self._repo.save_purchase_order(updated)

    # recepciones

    def create_receipt(
        self, *, supplier_party_id: int, purchase_order_id: int | None = None,
        document_reference: str | None = None,
    ) -> PurchaseReceipt:
        if purchase_order_id is not None:
            self.get_order(purchase_order_id)  # 404 temprano si no existe
        receipt = PurchaseReceipt(
            id=None, supplier_party_id=supplier_party_id, items=(),
            purchase_order_id=purchase_order_id, document_reference=document_reference,
        )
        return self._repo.save_purchase_receipt(receipt)

    def get_receipt(self, receipt_id: int) -> PurchaseReceipt:
        receipt = self._repo.get_purchase_receipt(receipt_id)
        if receipt is None:
            raise PurchaseReceiptNotFound(receipt_id)
        return receipt

    def list_receipts(self) -> list[PurchaseReceipt]:
        return list(self._repo.list_purchase_receipts())

    def add_receipt_item(
        self, receipt_id: int, *, item_id: int, quantity: Decimal, unit_cost: Decimal,
        lot_code: str | None = None, expires_at: datetime | None = None,
    ) -> PurchaseReceipt:
        receipt = self.get_receipt(receipt_id)
        if receipt.status != PurchaseReceiptStatus.DRAFT:
            raise InvalidPurchaseState(
                f"la recepcion {receipt_id} no esta en borrador (status={receipt.status})"
            )
        line = PurchaseReceiptItem(
            item_id=item_id, quantity=quantity, unit_cost=unit_cost,
            lot_code=lot_code, expires_at=expires_at,
        )
        updated = replace(receipt, items=receipt.items + (line,))
        return self._repo.save_purchase_receipt(updated)

    def confirm_receipt(self, receipt_id: int, *, location_id: int) -> PurchaseReceipt:
        receipt = self.get_receipt(receipt_id)
        if receipt.status != PurchaseReceiptStatus.DRAFT:
            raise InvalidPurchaseState(
                f"la recepcion {receipt_id} no esta en borrador (status={receipt.status})"
            )
        if not receipt.items:
            raise InvalidPurchaseState("no se puede confirmar una recepcion sin lineas")
        return confirm_purchase_receipt(self._repo, receipt, location_id, datetime.now(timezone.utc))
