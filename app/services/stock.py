"""Movimientos de stock manuales (ajustes) sobre SqliteCommerceRepository.

Los movimientos generados por una venta confirmada viven en
app/services/sales.py::confirm_sale -- este servicio es solo para el ajuste
manual que un admin puede necesitar (rotura, conteo fisico, etc).
"""
from datetime import UTC, datetime, timezone
from decimal import Decimal

from libracommerce.domain.inventory import StockMovement, StockMovementType
from libracore.db.core import Conexion

from ..commerce import repositorio


class StockService:
    def __init__(self, conn: Conexion):
        self._repo = repositorio(conn)

    def adjust(
        self, item_id: int, location_id: int, quantity_delta: Decimal, reason: str = "",
        *, variant_id: int | None = None,
    ) -> StockMovement:
        movement = StockMovement(
            id=None,
            item_id=item_id,
            variant_id=variant_id,
            location_id=location_id,
            movement_type=StockMovementType.ADJUSTMENT,
            quantity_delta=quantity_delta,
            occurred_at=datetime.now(UTC),
            source_type="manual_adjustment",
        )
        return self._repo.append_stock_movement(movement)

    def current_stock(self, item_id: int, location_id: int, *, variant_id: int | None = None) -> Decimal:
        return self._repo.current_stock(item_id, location_id, variant_id=variant_id)

    def movements(self, item_id: int, location_id: int, *, variant_id: int | None = None) -> list[StockMovement]:
        return list(self._repo.list_stock_movements(item_id, location_id, variant_id=variant_id))
