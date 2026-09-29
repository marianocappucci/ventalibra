"""Sucursales: lo que VentaLibra lee de `branches` (`libracommerce` ADR-012/013).

Desde la fase 1 de la jerarquía (2026-09-28) una sucursal es una entidad propia y el stock vive sólo en sus
depósitos (`locations.branch_id`). Las rutas son las del motor (`build_sucursales_router`,
`build_depositos_router`) y las reglas de este producto viven como ganchos en `app/depositos_ganchos.py`; queda
acá la lectura que necesitan los ganchos de cajas y turnos (`app/cajas_ganchos.py`) y el cierre diario."""

from libracommerce.domain.inventory import Branch
from libracore.db.core import Conexion

from ..commerce import repositorio


class SucursalService:
    def __init__(self, conn: Conexion):
        self._repo = repositorio(conn)

    def get(self, sucursal_id: int) -> Branch | None:
        return self._repo.get_branch(sucursal_id)

    def list(self, *, incluir_inactivas: bool = False) -> list[Branch]:
        """Sólo las activas por defecto — lo que esperan el POS y la validación de alta de cajas."""
        return list(self._repo.list_branches(active_only=not incluir_inactivas))
