"""Ubicaciones (deposito/sucursal): wrapper sobre SqliteCommerceRepository.

El repositorio ya resuelve alta/edicion/lectura por id; falta el listado.

**La edición (`update`) NO reimplementa las guardas de "a lo sumo un default"
ni "no desactivar el default"**: esas ya viven en `libracommerce.erp.catalogo`
(`update_deposito`/`set_default_deposito`, motor v0.17.0) porque las
sucursales de VentaLibra SON los `Location` del motor, y otros productos de la
familia (Contalibra, Restolibra) comparten el mismo dato. Lo único propio de
acá es la guarda de turno abierto (`SucursalConTurnoAbierto`), que el motor no
puede conocer -- no tiene idea de qué es un turno de caja.

🔴 Hay un pendiente conocido en el motor (B.4: `save_location` y
`get_default_deposito_id` no miran `active`) -- no se lo tapa acá: sencillamente
`update()` nunca llama a `save_location` para tocar `active`/`is_default`, así
que no pasa por ese camino sin guarda."""

from dataclasses import replace

from libracommerce.domain.inventory import Location
from libracommerce.erp.catalogo import set_default_deposito, update_deposito
from libracore.db.core import Conexion

from ..commerce import repositorio
from . import cajas as cajas_service


class LocationNotFound(Exception):
    """No existe una sucursal con ese id."""


class SucursalConTurnoAbierto(ValueError):
    """No se puede desactivar una sucursal con un turno de caja abierto en
    alguna de sus cajas -- guarda propia de VentaLibra (ver
    `app/services/cajas.py::tiene_turno_abierto_en`), el motor no sabe nada
    de turnos."""


class DatosInvalidos(ValueError):
    """Nombre o tipo vacíos -- se valida ACÁ, antes de llamar al motor, para
    que el router la distinga de la `ValueError` que levantan
    `update_deposito`/`set_default_deposito` (esas son 409: un conflicto con
    el estado de otra sucursal, no un dato mal formado del pedido)."""


class LocationService:
    def __init__(self, conn: Conexion):
        self._conn = conn
        self._repo = repositorio(conn)

    def create(self, name: str, location_type: str = "warehouse", branch_id: int | None = None) -> Location:
        location = Location(id=None, name=name, branch_id=branch_id, location_type=location_type)
        return self._repo.save_location(location)

    def get(self, location_id: int) -> Location | None:
        return self._repo.get_location(location_id)

    def list(self, *, incluir_inactivas: bool = False) -> list[Location]:
        """Sólo activas por defecto -- lo que ya esperan el POS y la validación
        de alta de cajas. `incluir_inactivas=True` es para la pantalla de
        edición (`Sucursales.tsx`): sin esto, una sucursal recién desactivada
        desaparecía de la lista y nadie podía reactivarla."""
        if incluir_inactivas:
            rows = self._conn.execute("SELECT id FROM locations ORDER BY name").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id FROM locations WHERE active = 1 ORDER BY name"
            ).fetchall()
        return [self._repo.get_location(row[0]) for row in rows]

    def update(self, location_id: int, name: str, location_type: str,
               is_default: bool, active: bool) -> Location:
        """Edita nombre, tipo, default y estado de una sucursal existente.

        Levanta `LocationNotFound` (404), `DatosInvalidos` (422, nombre/tipo
        vacío), `SucursalConTurnoAbierto` (409, la única guarda propia de acá)
        y `ValueError` liso (409, las guardas del motor sobre default) -- el
        router (`routers/locations.py`) traduce cada una."""
        location = self._repo.get_location(location_id)
        if location is None:
            raise LocationNotFound(f"No existe la sucursal {location_id}.")

        nombre = name.strip()
        if not nombre:
            raise DatosInvalidos("El nombre es obligatorio.")
        tipo = location_type.strip()
        if not tipo:
            raise DatosInvalidos("El tipo de sucursal es obligatorio.")

        # Combinaciones que el motor rechazaría a MITAD de camino (después de
        # que `update_deposito` ya escribió): se frenan antes de tocar nada.
        if not is_default and location.is_default:
            # Sin default, `get_default_deposito_id` cae a `ORDER BY id LIMIT 1`
            # sin mirar `active` (B.4) -- y de eso vive `ganchos.validar_deposito`.
            raise ValueError(
                "No se puede dejar la instancia sin sucursal predeterminada: "
                "marcá otra como predeterminada."
            )
        if is_default and not active:
            raise ValueError("Una sucursal inactiva no puede ser la predeterminada.")

        # Guarda propia de VentaLibra: se mira ANTES de tocar nada, contra el
        # estado de turnos actual (independiente de lo que venga en `active`).
        if not active and location.active and cajas_service.tiene_turno_abierto_en(location_id):
            raise SucursalConTurnoAbierto(
                f"No se puede desactivar la sucursal {location_id!r}: tiene un "
                "turno de caja abierto."
            )

        # `update_deposito` guarda nombre + activo, y ya rechaza desactivar el
        # depósito default (levanta `ValueError`, que el router traduce a 409).
        # Preserva `location_type`/`branch_id`/`is_default` tal cual estaban.
        update_deposito(self._conn, location_id, nombre, location.description, int(active))

        # `location_type` no lo toca `update_deposito` -- se escribe aparte,
        # directo por `save_location`: no hay ninguna guarda del motor que lo
        # alcance (sólo cubre `active`/`is_default`), así que no es el camino
        # que el pendiente B.4 advierte.
        if tipo != location.location_type:
            actual = self._repo.get_location(location_id)
            self._repo.save_location(replace(actual, location_type=tipo))

        if is_default and not location.is_default:
            # `set_default_deposito` ya rechaza marcar default una sucursal
            # inactiva -- si este mismo request también la activa, el UPDATE
            # de arriba ya corrió, así que ve el estado nuevo.
            set_default_deposito(self._conn, location_id)

        return self._repo.get_location(location_id)
