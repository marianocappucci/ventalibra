"""Listas de precio: wrapper fino sobre SqliteCommerceRepository.

resolve_price() delega enteramente en libracommerce -- ver
wiki/entities/libracommerce.md, seccion "Fase 4 de VentaLibra: Listas de
precio". Este servicio solo traduce entre la API HTTP y el repositorio.
"""
import sqlite3
from datetime import datetime
from decimal import Decimal

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.domain.catalog import ItemPrice, PriceList


class PricingService:
    def __init__(self, conn: sqlite3.Connection):
        self._repo = SqliteCommerceRepository(conn)

    def create_price_list(self, name: str, description: str = "", is_default: bool = False) -> PriceList:
        return self._repo.save_price_list(PriceList(id=None, name=name, description=description, is_default=is_default))

    def get_price_list(self, price_list_id: int) -> PriceList | None:
        return self._repo.get_price_list(price_list_id)

    def set_item_price(
        self, item_id: int, price_list_id: int, amount: Decimal, *,
        valid_from: datetime, valid_until: datetime | None = None,
        min_quantity: Decimal | None = None, branch_id: int | None = None,
    ) -> ItemPrice:
        item_price = ItemPrice(
            id=None, item_id=item_id, price_list_id=price_list_id, amount=amount,
            valid_from=valid_from, valid_until=valid_until,
            min_quantity=min_quantity, branch_id=branch_id,
        )
        return self._repo.save_item_price(item_price)

    def list_item_prices(self, item_id: int) -> list[ItemPrice]:
        return list(self._repo.list_item_prices(item_id))

    def resolve_price(
        self, item_id: int, *, price_list_id: int | None = None,
        quantity: Decimal = Decimal("1"), branch_id: int | None = None,
    ) -> Decimal | None:
        return self._repo.resolve_price(
            item_id, price_list_id=price_list_id, quantity=quantity, branch_id=branch_id
        )
