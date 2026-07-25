"""Caso de uso de venta POS: la orquestacion que SqliteCommerceRepository
deliberadamente no hace sola (ver wiki/entities/libracommerce.md, seccion
"Decisiones de esta ronda" -- confirmar una venta no dispara stock por
diseno, queda para la capa de casos de uso del producto consumidor).

Flujo: crear venta en borrador -> agregar lineas (snapshot de precio/costo
del CatalogItem al momento de agregarla) -> confirmar (recalcula totales,
fija confirmed_at, y por cada linea de tipo "product" genera un
StockMovement de tipo "sale" con cantidad negativa en la ubicacion dada).
"""
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.domain.catalog import CatalogItemType
from libracommerce.domain.inventory import StockMovement, StockMovementType
from libracommerce.domain.sales import Sale, SaleItem, SaleStatus


class SaleNotFound(Exception):
    pass


class InvalidSaleState(Exception):
    pass


def _next_sale_number(conn: sqlite3.Connection) -> str:
    """Numeracion propia sobre la tabla local_sequences ya presente en el
    esquema de LibraCommerce (usada tambien por su especificacion offline,
    con nombres de secuencia distintos -- no colisiona)."""
    row = conn.execute(
        "SELECT next_value FROM local_sequences WHERE name = ?", ("tiendalibra_sale",)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO local_sequences (name, next_value) VALUES (?, 2)",
            ("tiendalibra_sale",),
        )
        sequence = 1
    else:
        sequence = row[0]
        conn.execute(
            "UPDATE local_sequences SET next_value = ? WHERE name = ?",
            (sequence + 1, "tiendalibra_sale"),
        )
    return f"POS-{sequence:06d}"


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
        confirmed = replace(
            sale, status=SaleStatus.CONFIRMED, confirmed_at=datetime.now(timezone.utc),
        )
        saved = self._save_with_totals(confirmed)
        for line in saved.items:
            if line.kind == CatalogItemType.PRODUCT:
                movement = StockMovement(
                    id=None, item_id=line.item_id, location_id=location_id,
                    movement_type=StockMovementType.SALE,
                    quantity_delta=-line.quantity,
                    occurred_at=saved.confirmed_at,
                    source_type="sale", source_id=saved.id,
                )
                self._repo.append_stock_movement(movement)
        return saved

    def _save_with_totals(self, sale: Sale) -> Sale:
        subtotal = sum((item.quantity * item.unit_price for item in sale.items), Decimal("0"))
        discount_total = sum((item.discount_amount for item in sale.items), Decimal("0"))
        tax_total = sum((item.tax_amount for item in sale.items), Decimal("0"))
        totaled = replace(
            sale, subtotal=subtotal, discount_total=discount_total,
            tax_total=tax_total, total=sale.calculated_total(),
        )
        return self._repo.save_sale(totaled)
