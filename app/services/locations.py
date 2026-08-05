"""Ubicaciones (deposito/sucursal): wrapper sobre SqliteCommerceRepository.

El repositorio ya resuelve alta/edicion/lectura por id; falta el listado.
"""
import sqlite3

from ..commerce import repositorio
from libracommerce.domain.inventory import Location


class LocationService:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._repo = repositorio(conn)

    def create(self, name: str, location_type: str = "warehouse", branch_id: int | None = None) -> Location:
        location = Location(id=None, name=name, branch_id=branch_id, location_type=location_type)
        return self._repo.save_location(location)

    def get(self, location_id: int) -> Location | None:
        return self._repo.get_location(location_id)

    def list(self) -> list[Location]:
        rows = self._conn.execute(
            "SELECT id FROM locations WHERE active = 1 ORDER BY name"
        ).fetchall()
        return [self._repo.get_location(row[0]) for row in rows]
