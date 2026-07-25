"""Movimientos de stock manuales (ajustes) sobre SqliteCommerceRepository.

Los movimientos generados por una venta confirmada viven en
app/services/sales.py::confirm_sale -- este servicio es solo para el ajuste
manual que un admin puede necesitar (rotura, conteo fisico, etc).
"""
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.domain.inventory import StockMovement, StockMovementType


class StockService:
    def __init__(self, conn: sqlite3.Connection):
        self._repo = SqliteCommerceRepository(conn)

    def adjust(self, item_id: int, location_id: int, quantity_delta: Decimal, reason: str = "") -> StockMovement:
        movement = StockMovement(
            id=None,
            item_id=item_id,
            location_id=location_id,
            movement_type=StockMovementType.ADJUSTMENT,
            quantity_delta=quantity_delta,
            occurred_at=datetime.now(timezone.utc),
            source_type="manual_adjustment",
        )
        return self._repo.append_stock_movement(movement)

    def current_stock(self, item_id: int, location_id: int) -> Decimal:
        return self._repo.current_stock(item_id, location_id)

    def movements(self, item_id: int, location_id: int) -> list[StockMovement]:
        return list(self._repo.list_stock_movements(item_id, location_id))
