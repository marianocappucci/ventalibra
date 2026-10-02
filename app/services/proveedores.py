"""El puente entre el proveedor del motor y el party de las compras.

El proveedor vive en `proveedores` (`libracore.db.egresos`, el modelo de Contalibra: ADR-028/030). Las
órdenes y recepciones de compra de LibraCommerce apuntan a `parties` (`supplier_party_id`), y la convención
del motor (`libracommerce/scripts/migrate_from_contalibra.py`) es que **el party de un proveedor tiene
id `proveedores.id + 100.000`**. Esa regla vive SÓLO acá.

El party espejo se crea (o se refresca) **al comprarle**: el router del motor
(`/api/proveedores`) no sabe de compras, así que el proveedor puede nacer sin party.
"""

from libracore.db import egresos as db_egresos
from libracore.db.core import Conexion

#: `parties.id = proveedores.id + OFFSET_PROVEEDOR`.
OFFSET_PROVEEDOR = 100_000


class ProveedorNoExiste(Exception):
    """No hay un proveedor con ese id."""


def party_de_proveedor(conn: Conexion, proveedor_id: int) -> int:
    """El `parties.id` del proveedor, con su espejo al día. Levanta `ProveedorNoExiste`."""
    proveedor = db_egresos.get_proveedor(proveedor_id)
    if proveedor is None:
        raise ProveedorNoExiste(f"No existe el proveedor {proveedor_id}.")
    party_id = OFFSET_PROVEEDOR + proveedor_id
    conn.execute(
        "INSERT INTO parties (id, party_type, display_name, tax_id, email, phone, active) "
        "VALUES (?, 'organization', ?, ?, ?, ?, 1) "
        "ON CONFLICT (id) DO UPDATE SET display_name = EXCLUDED.display_name, "
        "tax_id = EXCLUDED.tax_id, email = EXCLUDED.email, phone = EXCLUDED.phone",
        (party_id, proveedor["nombre"], proveedor.get("cuit_dni") or None,
         proveedor.get("email") or None, proveedor.get("phone") or None),
    )
    conn.commit()
    return party_id


def proveedor_de_party(party_id: int) -> int:
    """El `proveedores.id` de un `supplier_party_id` de compras."""
    return party_id - OFFSET_PROVEEDOR


def es_proveedor_habitual(conn: Conexion, proveedor_id: int) -> bool:
    """Si algún producto lo tiene como proveedor habitual (reposición, ADR-056): no se puede eliminar sin soltarlo antes."""
    fila = conn.execute(
        "SELECT EXISTS(SELECT 1 FROM catalog_items WHERE supplier_party_id = ?)", (OFFSET_PROVEEDOR + proveedor_id,)
    ).fetchone()
    return bool(fila[0])


def tiene_compras(conn: Conexion, proveedor_id: int) -> bool:
    """Si el proveedor tiene órdenes o recepciones de compra (no se puede eliminar)."""
    party_id = OFFSET_PROVEEDOR + proveedor_id
    fila = conn.execute(
        "SELECT EXISTS(SELECT 1 FROM purchase_orders WHERE supplier_party_id = ?) "
        "OR EXISTS(SELECT 1 FROM purchase_receipts WHERE supplier_party_id = ?)",
        (party_id, party_id),
    ).fetchone()
    return bool(fila[0])
