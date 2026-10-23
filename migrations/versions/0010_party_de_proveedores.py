"""party_de_proveedores: crea el party de cada proveedor que ya existe (ADR-093).

Las órdenes y recepciones de compra apuntan a `parties` (`supplier_party_id = proveedores.id + 100000`, `app/services/
proveedores.py`). Hasta ahora el party nacía **al comprarle** al proveedor; desde que los proveedores y las órdenes de compra
bajan a los nodos (el nodo no escribe `parties` de proveedores: sólo verifica que haya bajado), el party tiene que existir
desde que el proveedor existe. El alta y la edición lo hacen de acá en más (`app/proveedores_guarda.py`); esta revisión
completa los proveedores que ya estaban cargados.

🔴 Corre DESPUÉS de las cadenas de LibraCore (crea `proveedores`) y de LibraCommerce (crea `parties`): así está declarado el
orden de `migraciones`. Es sólo datos: no agrega ni cambia ninguna columna. **Idempotente** y sin reescribir lo que ya está al
día (no dispara el changelog de LibraEdge para nada). **En un nodo no hace nada**: el party baja por el espejo con el resto de
la referencia. El `downgrade` no hace nada a propósito: un party de más no rompe nada y una orden de compra lo referencia.
"""
from alembic import op
from libracore.db.migraciones import conexion_libracore

from app.offline import nodo
from app.services.proveedores import sincronizar_parties_de_proveedores

revision = "0010_party_de_proveedores"
down_revision = "0009_libraedge"
branch_labels = None
depends_on = None


def upgrade():
    if nodo() is not None:
        return
    sincronizar_parties_de_proveedores(conexion_libracore(op.get_bind()))


def downgrade():
    pass
