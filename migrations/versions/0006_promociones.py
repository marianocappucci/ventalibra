"""promociones: «llevá N pagá M» y combos, y lo que se aplicó en cada venta.

`promotions`, `promotion_items` y `sale_promotions` son del motor desde el
2026-09-28 (ADR-012 de libracommerce, `erp.schema.crear_promociones`, mismo
criterio que `crear_cliente_lista_precio` de la `0005`). Es construcción nueva
—segundo ítem del roadmap de producto—, no una extracción: ningún producto de
la familia las tenía. VentaLibra las monta con `OpcionesVentas(promociones=True)`
(ADR-043).

Llamada por esta revisión y por `app/services/billing.py::configure()` — la
MISMA función en las dos puntas, para que una instancia nueva (nace de la
cadena) y una vieja (nació del arranque) no diverjan.

🔴 Corre DESPUÉS de `libracommerce-migrar` (crea `catalog_items` y `sales`, a
los que apuntan las FK): así está declarado el orden de `migraciones`.
"""
from alembic import op
from libracommerce.erp.schema import crear_promociones
from libracore.db.migraciones import conexion_libracore

revision = "0006_promociones"
down_revision = "0005_cliente_lista_precio"
branch_labels = None
depends_on = None


def upgrade():
    conn = conexion_libracore(op.get_bind())
    crear_promociones(conn)


def downgrade():
    op.drop_table("sale_promotions")
    op.drop_table("promotion_items")
    op.drop_table("promotions")
