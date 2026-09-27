"""Ubicaciones (sucursal/depósito): lo que VentaLibra necesita saber de `locations` por dentro.

Desde la fase 6 (2026-09-26, ADR-033) las rutas son las del motor (`build_depositos_router`, de `libracommerce`) y las
reglas de este producto viven como ganchos en `app/depositos_ganchos.py`. Queda acá lo que el resto de la app usa
directo: los dos tipos, `vende()`, el alta al arrancar de la sucursal y el depósito mínimos, y la lectura de
sucursales que necesitan los ganchos de cajas y turnos (`app/cajas_ganchos.py`)."""

from libracommerce.domain.inventory import Location
from libracore.db.core import Conexion

from ..commerce import repositorio

#: Sólo una sucursal `store` vende (decisión del humano, 2026-09-25): tiene
#: cajas, se ofrece en el POS y admite turnos. El depósito (`warehouse`) sólo
#: guarda stock; sus cajas históricas se conservan pero no operan.
TIPO_QUE_VENDE = "store"
TIPO_DEPOSITO = "warehouse"
#: Los dos únicos tipos (decisión del humano, 2026-09-25): un depósito es un
#: depósito y una sucursal es una sucursal; el nombre es lo que las distingue a
#: la vista. Toda instancia tiene como mínimo una de cada una.
TIPOS_VALIDOS = (TIPO_QUE_VENDE, TIPO_DEPOSITO)


def vende(location: Location) -> bool:
    return location.location_type == TIPO_QUE_VENDE


class LocationService:
    def __init__(self, conn: Conexion):
        self._conn = conn
        self._repo = repositorio(conn)

    def create(self, name: str, location_type: str = TIPO_DEPOSITO, branch_id: int | None = None) -> Location:
        location = Location(id=None, name=name, branch_id=branch_id, location_type=location_type)
        return self._repo.save_location(location)

    def _activas_de_tipo(self, tipo: str, *, sin: int | None = None) -> int:
        return sum(
            1 for loc in self.list()
            if loc.location_type == tipo and loc.id != sin
        )

    def asegurar_tipos_minimos(self) -> list[str]:
        """Al arrancar: si la instancia no tiene ninguna sucursal o ningún
        depósito activos, crea «Sucursal 1» / «Depósito 1». Idempotente: en una
        instancia que ya tiene las dos no toca nada. No cambia el default."""
        creadas = []
        for tipo, nombre in ((TIPO_QUE_VENDE, "Sucursal 1"), (TIPO_DEPOSITO, "Depósito 1")):
            if self._activas_de_tipo(tipo) == 0:
                self.create(nombre, tipo)
                creadas.append(nombre)
        return creadas

    def get(self, location_id: int) -> Location | None:
        return self._repo.get_location(location_id)

    def list(self, *, incluir_inactivas: bool = False) -> list[Location]:
        """Sólo activas por defecto -- lo que ya esperan el POS y la validación
        de alta de cajas. `incluir_inactivas=True` trae también las dadas de baja."""
        if incluir_inactivas:
            rows = self._conn.execute("SELECT id FROM locations ORDER BY name").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id FROM locations WHERE active = 1 ORDER BY name"
            ).fetchall()
        return [self._repo.get_location(row[0]) for row in rows]
