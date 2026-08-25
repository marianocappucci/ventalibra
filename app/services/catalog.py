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

from ..conexion import conexion_utilizable
from ..commerce import repositorio
from libracommerce.domain.catalog import (
    CatalogItem,
    CatalogItemType,
    Category,
    ItemCode,
    ItemCodeType,
    ItemVariant,
    Unit,
)
from libracore.db.core import Conexion


class CatalogService:
    def __init__(self, conn: Conexion):
        self._conn = conn
        self._repo = repositorio(conn)

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
        try:
            self._conn.execute(
                "INSERT INTO units (code, name, allows_fraction, decimal_scale) VALUES (?, ?, ?, ?)",
                (unit.code, unit.name, int(unit.allows_fraction), unit.decimal_scale),
            )
        except sqlite3.IntegrityError:
            # El INSERT que falla por UNIQUE(code) deja abierta la transaccion
            # implicita que sqlite3 abrio para ejecutarlo, con el lock de
            # escritura tomado. La conexion es una sola para toda la app, asi
            # que sin este rollback el 409 se lleva puesto al que escriba
            # despues. El router la traduce a HTTP.
            self._conn.rollback()
            raise
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

    # item codes (codigos de barra, sku, etc)

    def add_code(
        self, item_id: int, code_type: ItemCodeType, code: str, *, is_primary: bool = False
    ) -> ItemCode:
        item_code = ItemCode(id=None, item_id=item_id, code_type=code_type, code=code, is_primary=is_primary)
        # UNIQUE(code_type, code) y el indice de un solo primario por item. Ver
        # `app/conexion.py`: sin el rollback el 409 deja la app sin escribir.
        with conexion_utilizable(self._conn):
            return self._repo.save_item_code(item_code)

    def list_codes(self, item_id: int) -> list[ItemCode]:
        return list(self._repo.list_item_codes(item_id))

    def find_by_code(self, code: str) -> CatalogItem | None:
        return self._repo.find_item_by_code(code)

    # item variants (talle/color, presentaciones)

    def add_variant(
        self, item_id: int, sku: str, name: str, *, attributes: dict[str, str] | None = None
    ) -> ItemVariant:
        variant = ItemVariant(id=None, item_id=item_id, sku=sku, name=name, attributes=attributes or {})
        # UNIQUE(sku) — mismo motivo que `add_code`.
        with conexion_utilizable(self._conn):
            return self._repo.save_item_variant(variant)

    def list_variants(self, item_id: int) -> list[ItemVariant]:
        return list(self._repo.list_item_variants(item_id))

    def get_variant(self, variant_id: int) -> ItemVariant | None:
        return self._repo.get_item_variant(variant_id)

    def _get_unit(self, unit_code: str) -> Unit:
        row = self._conn.execute(
            "SELECT code, name, allows_fraction, decimal_scale FROM units WHERE code = ?",
            (unit_code,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unidad desconocida: {unit_code!r}")
        return Unit(code=row[0], name=row[1], allows_fraction=bool(row[2]), decimal_scale=row[3])
