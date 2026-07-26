"""Caso de uso de venta POS.

Confirmar una venta delega en libracommerce.usecases.sales.confirm_sale
(v0.1.2) -- antes esta orquestacion (stock por cada linea de producto) se
reimplementaba aca porque LibraCommerce todavia no la ofrecia. Ver
wiki/entities/libracommerce.md, seccion "Capa de casos de uso".

Flujo: crear venta en borrador -> agregar lineas (snapshot de precio/costo
del CatalogItem al momento de agregarla) -> confirmar.
"""
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.domain.sales import Sale, SaleItem, SaleStatus
from libracommerce.usecases.sales import confirm_sale

from ..db import next_sequence


class SaleNotFound(Exception):
    pass


class InvalidSaleState(Exception):
    pass


def _next_sale_number(conn: sqlite3.Connection) -> str:
    return f"POS-{next_sequence(conn, 'ventalibra_sale'):06d}"


class SaleService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._repo = SqliteCommerceRepository(conn)

    def create_draft(
        self, *, branch_id: int | None = None, register_id: int | None = None,
        customer_party_id: int | None = None,
    ) -> Sale:
        number = _next_sale_number(self._conn)
        sale = Sale(
            id=None, number=number, items=(), status=SaleStatus.DRAFT,
            branch_id=branch_id, register_id=register_id, customer_party_id=customer_party_id,
        )
        return self._repo.save_sale(sale)

    def get(self, sale_id: int) -> Sale:
        sale = self._repo.get_sale(sale_id)
        if sale is None:
            raise SaleNotFound(sale_id)
        return sale

    def add_item(
        self, sale_id: int, *, item_id: int, quantity: Decimal,
        unit_price: Decimal | None = None, discount_amount: Decimal = Decimal("0"),
    ) -> Sale:
        sale = self.get(sale_id)
        if sale.status != SaleStatus.DRAFT:
            raise InvalidSaleState(f"la venta {sale_id} no esta en borrador (status={sale.status})")
        catalog_item = self._repo.get_catalog_item(item_id)
        if catalog_item is None:
            raise KeyError(f"item de catalogo desconocido: {item_id}")
        price = unit_price if unit_price is not None else catalog_item.default_sale_price
        line = SaleItem(
            kind=catalog_item.item_type,
            item_id=catalog_item.id,
            description_snapshot=catalog_item.name,
            quantity=quantity,
            unit_price=price,
            discount_amount=discount_amount,
            unit_cost_snapshot=catalog_item.default_cost,
        )
        updated = replace(sale, items=sale.items + (line,))
        return self._save_with_totals(updated)

    def confirm(self, sale_id: int, *, location_id: int) -> Sale:
        sale = self.get(sale_id)
        if sale.status != SaleStatus.DRAFT:
            raise InvalidSaleState(f"la venta {sale_id} no esta en borrador (status={sale.status})")
        if not sale.items:
            raise InvalidSaleState("no se puede confirmar una venta sin lineas")
        return confirm_sale(self._repo, sale, location_id, datetime.now(timezone.utc))

    def _save_with_totals(self, sale: Sale) -> Sale:
        subtotal = sum((item.quantity * item.unit_price for item in sale.items), Decimal("0"))
        discount_total = sum((item.discount_amount for item in sale.items), Decimal("0"))
        tax_total = sum((item.tax_amount for item in sale.items), Decimal("0"))
        totaled = replace(
            sale, subtotal=subtotal, discount_total=discount_total,
            tax_total=tax_total, total=sale.calculated_total(),
        )
        return self._repo.save_sale(totaled)
