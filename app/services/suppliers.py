"""Proveedores, sobre el modelo del motor: `libracore.db.egresos` (tabla `proveedores`).

Desde la migración `0004` (2026-09-26) el proveedor vive en `proveedores` y su `parties` espejo
tiene el id **`proveedores.id + 100_000`** (la convención de
`libracommerce/scripts/migrate_from_contalibra.py`). El espejo existe porque las órdenes y
recepciones de compra de LibraCommerce apuntan a `parties` (`supplier_party_id`).

**El `id` que expone este servicio es el del party** (el `supplier_party_id` de las compras), para
no cambiar el contrato de `/suppliers` y de Compras en esta fase; la fase 3 lo reemplaza por el
router del motor (`/api/proveedores`, con el id de `proveedores`).
"""

from libracommerce.domain.entities import Party, PartyType
from libracore.db import egresos as db_egresos
from libracore.db.core import Conexion

#: `parties.id = proveedores.id + OFFSET_PROVEEDOR`.
OFFSET_PROVEEDOR = 100_000


def _a_party(proveedor: dict) -> Party:
    return Party(
        id=OFFSET_PROVEEDOR + proveedor["id"], party_type=PartyType.ORGANIZATION,
        display_name=proveedor["nombre"], legal_name=None,
        tax_id=proveedor.get("cuit_dni") or None, email=proveedor.get("email") or None,
        phone=proveedor.get("phone") or None, active=True,
    )


class SupplierService:
    def __init__(self, conn: Conexion):
        self._conn = conn

    def create(
        self, *, display_name: str, party_type: PartyType = PartyType.ORGANIZATION,
        legal_name: str | None = None, tax_id: str | None = None,  # noqa: ARG002
        email: str | None = None, phone: str | None = None,
    ) -> Party:
        proveedor_id = db_egresos.create_proveedor(
            display_name, cuit_dni=tax_id or "", email=email or "", phone=phone or "",
        )
        party_id = OFFSET_PROVEEDOR + proveedor_id
        self._conn.execute(
            "INSERT INTO parties (id, party_type, display_name, legal_name, tax_id, email, phone, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1) ON CONFLICT (id) DO NOTHING",
            (party_id, party_type.value, display_name, legal_name, tax_id or None,
             email or None, phone or None),
        )
        self._conn.commit()
        return _a_party(db_egresos.get_proveedor(proveedor_id))

    def get(self, party_id: int) -> Party | None:
        if party_id < OFFSET_PROVEEDOR:
            return None
        proveedor = db_egresos.get_proveedor(party_id - OFFSET_PROVEEDOR)
        return _a_party(proveedor) if proveedor is not None else None

    def list_all(self) -> list[Party]:
        return [_a_party(p) for p in db_egresos.get_all_proveedores()]
