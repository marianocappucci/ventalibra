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

from ..commerce import repositorio
from ..conexion import conexion_utilizable


class ItemNotFound(Exception):
    """404: no existe un CatalogItem con ese id."""


class ItemUnitLockedError(Exception):
    """409: el item ya tiene movimientos (stock, venta o compra) y se
    intento cambiarle la unidad. Cambiarla ahi cambiaria el significado de
    todo lo que esos movimientos ya registraron con la unidad vieja."""

    def __init__(self, item_id: int):
        self.item_id = item_id
        super().__init__(
            "No se puede cambiar la unidad de un producto que ya tiene movimientos."
        )


class ItemInvalido(Exception):
    """422: el item no cumple una regla de negocio -- nombre vacio, precio o
    costo negativo, o categoria inexistente. Separada de KeyError (que sigue
    siendo la unidad desconocida, en `_get_unit`) porque esa validacion es
    vieja y ya la traducian los dos endpoints; esta es la que create_item no
    tenia -- ver `_validar_item`."""


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
        nombre = self._validar_item(
            name=name, category_id=category_id,
            default_sale_price=default_sale_price, default_cost=default_cost,
        )
        item = CatalogItem(
            id=None,
            item_type=item_type,
            name=nombre,
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
            raise ItemNotFound(item_id)

        # `unit_code` no es un campo de CatalogItem (el campo es `unit`, un
        # Unit completo) -- se resuelve aca, igual que en create_item. Se
        # resuelve SIEMPRE, cambie o no: valida que la unidad exista (422,
        # mismo criterio que el alta) aunque el pedido no la este cambiando.
        unit_code = changes.pop("unit_code", item.unit.code)
        nueva_unidad = self._get_unit(unit_code)
        if nueva_unidad.code != item.unit.code and self.has_movements(item_id):
            # Cambiar u -> kg en un item que ya vendio o recibio stock deja
            # esos movimientos con una unidad que ya no es la del item --
            # ver ItemUnitLockedError. El resto de los campos se edita
            # siempre, este es el unico bloqueado.
            raise ItemUnitLockedError(item_id)
        changes["unit"] = nueva_unidad

        # Mismo helper que create_item -- nombre no vacio, categoria
        # existente y precio/costo no negativos. Antes esta edicion validaba
        # la categoria aca mismo (con KeyError) y el nombre/precio/costo los
        # validaba ItemUpdate con Field de Pydantic, dos formatos de error
        # distintos para el mismo 422. Ahora las tres viven en un solo lugar
        # y responden con el mismo `detail` en los dos endpoints.
        changes["name"] = self._validar_item(
            name=changes.get("name", item.name),
            category_id=changes.get("category_id", item.category_id),
            default_sale_price=changes.get("default_sale_price", item.default_sale_price),
            default_cost=changes.get("default_cost", item.default_cost),
        )

        return self._repo.save_catalog_item(replace(item, **changes))

    def has_movements(self, item_id: int) -> bool:
        """True si el item ya aparece en stock, una venta o una compra.

        Las cuatro tablas son las que graban `item_id` con la unidad puesta
        en el momento del movimiento: `stock_movements` (cualquier alta,
        ajuste o transferencia), `sale_items` (lo vendido), y las dos de
        compras -- `purchase_order_items` (lo pedido) y
        `purchase_receipt_items` (lo recibido), porque una orden sin
        recepcion todavia registro una cantidad en la unidad vieja.
        """
        row = self._conn.execute(
            """
            SELECT
                EXISTS(SELECT 1 FROM stock_movements WHERE item_id = ?)
                OR EXISTS(SELECT 1 FROM sale_items WHERE item_id = ?)
                OR EXISTS(SELECT 1 FROM purchase_order_items WHERE item_id = ?)
                OR EXISTS(SELECT 1 FROM purchase_receipt_items WHERE item_id = ?)
            """,
            (item_id, item_id, item_id, item_id),
        ).fetchone()
        return bool(row[0])

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

    def _category_exists(self, category_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        return row is not None

    def _validar_item(
        self,
        *,
        name: str,
        category_id: int | None,
        default_sale_price: Decimal,
        default_cost: Decimal,
    ) -> str:
        """Reglas de negocio compartidas por create_item y update_item.
        Devuelve el nombre ya sin espacios de sobra, para que el llamador lo
        use tal cual en vez de repetir el `.strip()`.

        La unidad NO esta aca: sigue resolviendose con `_get_unit`, que ya
        era compartida por los dos metodos y usa KeyError (422) desde antes
        de este cambio -- no hacia falta tocarla.
        """
        nombre = name.strip()
        if not nombre:
            raise ItemInvalido("el nombre no puede estar vacio")
        if category_id is not None and not self._category_exists(category_id):
            raise ItemInvalido(f"categoria desconocida: {category_id!r}")
        if default_sale_price < 0:
            raise ItemInvalido("el precio de venta no puede ser negativo")
        if default_cost < 0:
            raise ItemInvalido("el costo no puede ser negativo")
        return nombre
