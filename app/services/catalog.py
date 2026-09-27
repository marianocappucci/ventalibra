"""Administración de unidades y categorías del catálogo (Configuración).

Desde la fase 7 (2026-09-27, ADR-034) los productos son el router del motor (`app/productos_ganchos.py`); queda acá lo
que el motor no tiene: las unidades (código, nombre, si admiten fracciones, escala decimal) y las categorías
jerárquicas con baja lógica y nombre único entre las activas."""
import sqlite3

from libracommerce.domain.catalog import Category, Unit
from libracore.db.core import Conexion


class CategoryNotFound(Exception):
    """404: no existe una Category con ese id."""


class CategoryInvalido(Exception):
    """422: la categoria no cumple una regla de negocio -- nombre vacio o
    nombre repetido entre categorias activas. Recurso distinto de
    el nombre de un producto (que valida el gancho de productos) -- ver
    `_validar_category_name`."""


class CatalogService:
    def __init__(self, conn: Conexion):
        self._conn = conn

    # categories

    def create_category(self, name: str, parent_id: int | None = None) -> Category:
        nombre = self._validar_category_name(name)
        cur = self._conn.execute(
            "INSERT INTO categories (name, parent_id, active) VALUES (?, ?, 1)",
            (nombre, parent_id),
        )
        self._conn.commit()
        return Category(id=cur.lastrowid, name=nombre, parent_id=parent_id)

    def update_category(self, category_id: int, *, name: str, active: bool) -> Category:
        """`parent_id` queda afuera a proposito: esta pantalla (Configuracion >
        Categorias) no expone jerarquia -- nada en el producto arma un select
        de categoria padre -- asi que agregarlo a la edicion seria un campo
        sin donde cargarse. Si algun dia se expone, se suma aca."""
        category = self._get_category(category_id)
        if category is None:
            raise CategoryNotFound(category_id)
        nombre = self._validar_category_name(name, exclude_id=category_id)
        self._conn.execute(
            "UPDATE categories SET name = ?, active = ? WHERE id = ?",
            (nombre, int(active), category_id),
        )
        self._conn.commit()
        return Category(id=category_id, name=nombre, parent_id=category.parent_id, active=active)

    def list_categories(self) -> list[Category]:
        # SIN filtrar por active: a diferencia de list_items/list_units, esta
        # lista la consume tambien la pantalla de administracion de
        # categorias (Configuracion > Categorias), que tiene que poder ver
        # -y reactivar- las inactivas. Que el alta/edicion de producto solo
        # ofrezca las activas es responsabilidad del frontend (Productos.tsx),
        # no de este metodo -- ver el comentario ahi.
        rows = self._conn.execute(
            "SELECT id, name, parent_id, active FROM categories ORDER BY name"
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

    def _get_category(self, category_id: int) -> Category | None:
        row = self._conn.execute(
            "SELECT id, name, parent_id, active FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
        if row is None:
            return None
        return Category(id=row[0], name=row[1], parent_id=row[2], active=bool(row[3]))

    def _validar_category_name(self, name: str, *, exclude_id: int | None = None) -> str:
        """Nombre no vacio y no repetido entre categorias ACTIVAS -- compartida
        por create_category y update_category, mismo criterio que
        `_validar_item` con ItemInvalido.

        El UNIQUE(parent_id, name) de la tabla (libracommerce/db/schema.py) no
        alcanza solo: SQL no considera dos NULL iguales entre si, y esta
        pantalla no expone jerarquia -- `parent_id` es siempre None en el
        flujo real -- asi que dos categorias top-level con el mismo nombre
        pasan ese UNIQUE sin chocar. Por eso el chequeo se hace aca, contra
        las activas (desactivar libera el nombre para reusarlo), y no
        delegado al INSERT/UPDATE.
        """
        nombre = name.strip()
        if not nombre:
            raise CategoryInvalido("el nombre no puede estar vacio")
        query = "SELECT 1 FROM categories WHERE active = 1 AND name = ?"
        params: list = [nombre]
        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)
        if self._conn.execute(query, params).fetchone() is not None:
            raise CategoryInvalido(f"ya existe una categoria activa llamada {nombre!r}")
        return nombre
