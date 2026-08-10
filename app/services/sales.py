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

from ..commerce import repositorio
from libracommerce.domain.sales import Sale, SaleItem, SalePayment, SaleStatus
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
        self._repo = repositorio(conn)

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

    def list_recent(self, *, limit: int = 50, search: str = "") -> list[dict]:
        """Las últimas ventas, para encontrar una y poder deshacerla.

        Devuelve el encabezado nada más (sin líneas ni pagos): es una lista
        para buscar, y traer todo de cada venta la haría lenta sin que nadie
        lo mire. El detalle se pide con `get()` al abrir una.
        """
        sql = """
            SELECT id, number, status, status_detail, total, confirmed_at, occurred_on,
                   customer_name_snapshot
            FROM sales
            WHERE status != 'draft'
        """
        params: list = []
        if search:
            sql += " AND (number LIKE ? OR customer_name_snapshot LIKE ?)"
            params += [f"%{search}%", f"%{search}%"]
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [
            {
                "id": row[0], "number": row[1], "status": row[2],
                "status_detail": row[3], "total": Decimal(str(row[4] or 0)),
                "confirmed_at": row[5], "occurred_on": row[6],
                "cliente": row[7] or "",
            }
            for row in self._conn.execute(sql, params).fetchall()
        ]

    def get(self, sale_id: int) -> Sale:
        sale = self._repo.get_sale(sale_id)
        if sale is None:
            raise SaleNotFound(sale_id)
        return sale

    def add_item(
        self, sale_id: int, *, item_id: int, quantity: Decimal,
        variant_id: int | None = None, unit_price: Decimal | None = None,
        discount_amount: Decimal = Decimal("0"), price_list_id: int | None = None,
    ) -> Sale:
        sale = self._require_draft(sale_id)
        catalog_item = self._repo.get_catalog_item(item_id)
        if catalog_item is None:
            raise KeyError(f"item de catalogo desconocido: {item_id}")
        description = catalog_item.name
        if variant_id is not None:
            variant = self._repo.get_item_variant(variant_id)
            if variant is None or variant.item_id != item_id:
                raise KeyError(f"variante desconocida para el item {item_id}: {variant_id}")
            description = f"{catalog_item.name} ({variant.name})"
        price = unit_price
        if price is None:
            price = self._repo.resolve_price(item_id, price_list_id=price_list_id, quantity=quantity)
        if price is None:
            price = catalog_item.default_sale_price
        line = SaleItem(
            kind=catalog_item.item_type,
            item_id=catalog_item.id,
            variant_id=variant_id,
            description_snapshot=description,
            quantity=quantity,
            unit_price=price,
            discount_amount=discount_amount,
            unit_cost_snapshot=catalog_item.default_cost,
        )
        updated = replace(sale, items=sale.items + (line,))
        return self._save_with_totals(updated)

    def remove_item(self, sale_id: int, *, index: int) -> Sale:
        """Quita una linea del borrador. Se identifica por POSICION y no por
        id porque `SaleItem` no tiene id propio: `save_sale` borra y reinserta
        todas las lineas en cada update, asi que el id de fila no es estable
        entre guardados."""
        sale = self._require_draft(sale_id)
        items = self._require_index(sale, index)
        return self._save_with_totals(
            replace(sale, items=items[:index] + items[index + 1:]),
        )

    def set_item_quantity(self, sale_id: int, *, index: int, quantity: Decimal) -> Sale:
        """Corrige la cantidad de una linea ya cargada. El precio unitario no
        se recalcula: se respeta el que quedo congelado al agregarla (puede
        venir de una lista de precios o haber sido puesto a mano)."""
        if quantity <= 0:
            raise InvalidSaleState("la cantidad debe ser mayor que cero")
        sale = self._require_draft(sale_id)
        items = self._require_index(sale, index)
        updated_line = replace(items[index], quantity=quantity)
        return self._save_with_totals(
            replace(sale, items=items[:index] + (updated_line,) + items[index + 1:]),
        )

    def set_customer(self, sale_id: int, *, customer_party_id: int | None) -> Sale:
        """Asigna (o quita) el cliente de una venta en borrador.

        Hace falta poder hacerlo con líneas ya cargadas: en el mostrador el
        cajero se entera de que la venta va fiada recién al cobrar, y para
        entonces la venta ya existe.
        """
        sale = self._require_draft(sale_id)
        return self._save_with_totals(replace(sale, customer_party_id=customer_party_id))

    def _require_draft(self, sale_id: int) -> Sale:
        sale = self.get(sale_id)
        if sale.status != SaleStatus.DRAFT:
            raise InvalidSaleState(f"la venta {sale_id} no esta en borrador (status={sale.status})")
        return sale

    def _require_index(self, sale: Sale, index: int) -> tuple[SaleItem, ...]:
        if index < 0 or index >= len(sale.items):
            raise IndexError(f"la venta no tiene una linea en la posicion {index}")
        return sale.items

    def confirm(
        self, sale_id: int, *, location_id: int,
        payments: tuple[SalePayment, ...] = (),
    ) -> Sale:
        sale = self._require_draft(sale_id)
        if not sale.items:
            raise InvalidSaleState("no se puede confirmar una venta sin lineas")
        if payments:
            # Cobrar de menos deja una venta a medio pagar, que este POS no
            # modela (no hay cuenta corriente en mostrador): se rechaza. De
            # mas si se acepta -- es el vuelto.
            cobrado = sum((pago.amount for pago in payments), Decimal("0"))
            if cobrado < sale.total:
                raise InvalidSaleState(
                    f"los pagos no cubren el total de la venta: cobrado={cobrado}, total={sale.total}"
                )
            sale = replace(sale, payments=tuple(payments))
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
