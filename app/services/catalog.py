"""Catalogo de VentaLibra: wrapper fino sobre SqliteCommerceRepository.

SqliteCommerceRepository ya resuelve alta/edicion/lectura por id de
CatalogItem, y hace upsert de Unit al guardar un item. No expone list_* ni
alta/lectura de Category (el dominio de LibraCommerce no incluye ese
repositorio publico todavia) -- esas consultas son responsabilidad del
consumidor, y viven aca.
"""
import sqlite3
from dataclasses import replace
from decimal import Decimal

from libracommerce.db.repository import SqliteCommerceRepository
from libracommerce.domain.catalog import CatalogItem, CatalogItemType, Category, Unit


class CatalogService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._repo = SqliteCommerceRepository(conn)

    # categories

    def create_category(self, name: str, parent_id: int | None = None) -> Category:
        cur = self._conn.execute(
            "INSERT INTO categories (name, parent_id, active) VALUES (?, ?, 1)",
            (name, parent_id),
        )
        self._conn.commit()
        return Category(id=cur.lastrowid, name=name, parent_id=parent_id)

    def list_categories(self) -> list[Category]:
        rows = self._conn.execute(
            "SELECT id, name, parent_id, active FROM categories WHERE active = 1 ORDER BY name"
        ).fetchall()
        return [
            Category(id=row[0], name=row[1], parent_id=row[2], active=bool(row[3]))
            for row in rows
        ]

    # units

    def create_unit(self, code: str, name: str, allows_fraction: bool = False, decimal_scale: int = 0) -> Unit:
        unit = Unit(code=code, name=name, allows_fraction=allows_fraction, decimal_scale=decimal_scale)
        self._conn.execute(
            "INSERT INTO units (code, name, allows_fraction, decimal_scale) VALUES (?, ?, ?, ?)",
            (unit.code, unit.name, int(unit.allows_fraction), unit.decimal_scale),
        )
        self._conn.commit()
        return unit

    def list_units(self) -> list[Unit]:
        rows = self._conn.execute(
            "SELECT code, name, allows_fraction, decimal_scale FROM units ORDER BY code"
        ).fetchall()
        return [
            Unit(code=row[0], name=row[1], allows_fraction=bool(row[2]), decimal_scale=row[3])
            for row in rows
        ]

    # catalog items

    def create_item(
        self,
        *,
        name: str,
        unit_code: str,
        item_type: CatalogItemType = CatalogItemType.PRODUCT,
        category_id: int | None = None,
        description: str = "",
        default_sale_price: Decimal = Decimal("0"),
        default_cost: Decimal = Decimal("0"),
    ) -> CatalogItem:
        unit = self._get_unit(unit_code)
        item = CatalogItem(
            id=None,
            item_type=item_type,
            name=name,
            unit=unit,
            category_id=category_id,
            description=description,
            default_sale_price=default_sale_price,
            default_cost=default_cost,
        )
        return self._repo.save_catalog_item(item)

    def update_item(self, item_id: int, **changes) -> CatalogItem:
        item = self.get_item(item_id)
        if item is None:
            raise KeyError(item_id)
        return self._repo.save_catalog_item(replace(item, **changes))

    def get_item(self, item_id: int) -> CatalogItem | None:
        return self._repo.get_catalog_item(item_id)

    def list_items(self, *, category_id: int | None = None, search: str | None = None) -> list[CatalogItem]:
        query = "SELECT id FROM catalog_items WHERE active = 1"
        params: list = []
        if category_id is not None:
            query += " AND category_id = ?"
            params.append(category_id)
        if search:
            query += " AND name LIKE ?"
            params.append(f"%{search}%")
        query += " ORDER BY name"
        rows = self._conn.execute(query, params).fetchall()
        return [self._repo.get_catalog_item(row[0]) for row in rows]

    def _get_unit(self, unit_code: str) -> Unit:
        row = self._conn.execute(
            "SELECT code, name, allows_fraction, decimal_scale FROM units WHERE code = ?",
            (unit_code,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unidad desconocida: {unit_code!r}")
        return Unit(code=row[0], name=row[1], allows_fraction=bool(row[2]), decimal_scale=row[3])
