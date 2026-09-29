"""backfill_cc_pago_id: liga los movimientos de pagos a cuenta viejos con su pago.

Completa `caja_movimientos.cc_pago_id` (columna de `libracore` `0013`) para los pagos anteriores a `libracore`
v1.117.0, a partir de la referencia `cc-pago-<id>` que VentaLibra les ponía. Detalle y criterio en
`app/cc_pago_backfill.py`.

🔴 Corre DESPUÉS de la cadena de LibraCore (crea la columna): así está declarado el orden de `migraciones`.

Es sólo datos: no agrega ni cambia ninguna columna. Idempotente. El `downgrade` no hace nada a propósito: dejar el
vínculo puesto no rompe nada y quitarlo dejaría sin baja limpia a los pagos que ya lo tenían.
"""
from alembic import op
from libracore.db.migraciones import conexion_libracore

from app.cc_pago_backfill import backfill_cc_pago_id

revision = "0008_backfill_cc_pago_id"
down_revision = "0007_sucursales_jerarquicas"
branch_labels = None
depends_on = None


def upgrade():
    backfill_cc_pago_id(conexion_libracore(op.get_bind()))


def downgrade():
    pass
