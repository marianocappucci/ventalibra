"""El puente entre el proveedor del motor y el party de las compras.

El proveedor vive en `proveedores` (`libracore.db.egresos`, el modelo de Contalibra: ADR-028/030). Las
órdenes y recepciones de compra de LibraCommerce apuntan a `parties` (`supplier_party_id`), y la convención
del motor (`libracommerce/scripts/migrate_from_contalibra.py`) es que **el party de un proveedor tiene
id `proveedores.id + 100.000`**. Esa regla vive SÓLO acá.

## Quién escribe el party (ADR-093)

**Sólo el central.** El router del motor (`/api/proveedores`) no sabe de compras, así que el party espejo lo mantiene el
producto: `sincronizar_parties_de_proveedores` lo crea o lo refresca al dar de alta o editar un proveedor
(`app/proveedores_guarda.py`), la migración `0010` lo completa para los que ya existían (backfill) y `party_de_proveedor`
lo asegura antes de cada orden o recepción. Todo es idempotente y **no toca la fila si ya está al día** (sin eso, cada
sincronización dispararía el changelog de LibraEdge para nada).

**En un nodo no se escribe `parties` de proveedores**: el party baja por el espejo con el resto de la referencia, y
`party_de_proveedor` sólo verifica que exista (`ProveedorSinSincronizar` si todavía no bajó). Escribirlo en el nodo lo dejaría
con una fila que el espejo del central pisa o choca.
"""

from libracore.db import egresos as db_egresos
from libracore.db.core import Conexion

#: `parties.id = proveedores.id + OFFSET_PROVEEDOR`.
OFFSET_PROVEEDOR = 100_000


class ProveedorNoExiste(Exception):
    """No hay un proveedor con ese id."""


class ProveedorSinSincronizar(Exception):
    """En un nodo: el proveedor existe pero su party todavía no bajó del central (el espejo no lo trajo)."""


#: El upsert del party de un proveedor. El `WHERE` hace que una fila que ya está al día no se reescriba: no dispara el
#: trigger del changelog de LibraEdge ni ensucia el espejo.
_UPSERT_PARTY = (
    "INSERT INTO parties (id, party_type, display_name, tax_id, email, phone, active) "
    "VALUES (?, 'organization', ?, ?, ?, ?, 1) "
    "ON CONFLICT (id) DO UPDATE SET display_name = EXCLUDED.display_name, "
    "tax_id = EXCLUDED.tax_id, email = EXCLUDED.email, phone = EXCLUDED.phone "
    "WHERE (parties.display_name, parties.tax_id, parties.email, parties.phone) "
    "IS DISTINCT FROM (EXCLUDED.display_name, EXCLUDED.tax_id, EXCLUDED.email, EXCLUDED.phone)"
)


def _datos_del_party(proveedor_id: int, nombre: str, cuit_dni, email, phone) -> tuple:
    return (OFFSET_PROVEEDOR + proveedor_id, nombre, cuit_dni or None, email or None, phone or None)


def sincronizar_parties_de_proveedores(conn: Conexion) -> int:
    """Crea o refresca el party de **cada** proveedor (el backfill y lo que corre al guardar uno). Devuelve cuántos proveedores
    hay. No commitea: es de quien llama. Sólo para el central (en un nodo el party baja por el espejo)."""
    proveedores = conn.execute("SELECT id, nombre, cuit_dni, email, phone FROM proveedores ORDER BY id").fetchall()
    for id_, nombre, cuit_dni, email, phone in proveedores:
        conn.execute(_UPSERT_PARTY, _datos_del_party(id_, nombre, cuit_dni, email, phone))
    return len(proveedores)


def party_de_proveedor(conn: Conexion, proveedor_id: int) -> int:
    """El `parties.id` del proveedor. En el central, con su espejo al día; en un nodo, sólo se verifica que exista.

    Levanta `ProveedorNoExiste`, y en un nodo `ProveedorSinSincronizar` si el party no bajó todavía."""
    from ..offline import nodo

    party_id = OFFSET_PROVEEDOR + proveedor_id
    if nodo() is not None:
        existe = conn.execute("SELECT 1 FROM parties WHERE id = ?", (party_id,)).fetchone()
        if existe is None:
            raise ProveedorSinSincronizar(
                f"El proveedor {proveedor_id} todavía no llegó a este equipo: esperá a que sincronice con el central.")
        return party_id
    proveedor = db_egresos.get_proveedor(proveedor_id)
    if proveedor is None:
        raise ProveedorNoExiste(f"No existe el proveedor {proveedor_id}.")
    conn.execute(_UPSERT_PARTY, _datos_del_party(
        proveedor_id, proveedor["nombre"], proveedor.get("cuit_dni"), proveedor.get("email"), proveedor.get("phone")))
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
