"""sucursales_jerarquicas: del modelo plano de ubicaciones al jerárquico (`libracommerce` ADR-012/013).

Cada `store` de `locations` pasa a ser una sucursal (`branches`) con el MISMO id, y su fila queda como su depósito
predeterminado: `cajas.sucursal_id`, los turnos, los precios por sucursal y el stock siguen apuntando a lo mismo
sin reescribir historia. Los depósitos sin dueño se asignan a la sucursal que diga el mapa o, sin mapa, a la
predeterminada; las cajas de un depósito pasan a su sucursal. Detalle y por qué en `app/sucursales_migracion.py`.

La lógica es esa función y no vive acá: `db.connect()` llama a `asegurar_minimas` (que la incluye) en cada
arranque y al restaurar un respaldo, y así una instancia nueva y una vieja convergen por el mismo camino.

**Mapa de depósitos** (opcional): `VENTALIBRA_DEPOSITOS_A_SUCURSAL="2:1,5:3"` asigna el depósito 2 a la sucursal 1
y el 5 a la 3 en vez de mandarlos a la predeterminada. El preflight (`scripts/preflight_jerarquia.py`) lista los
depósitos que necesitarían mapa.

🔴 Corre DESPUÉS de la cadena de LibraCore (crea `cajas`) y de `libracommerce.db.schema.init_schema()` (crea
`branches`, aplicado por `db.connect()` y por la `0003_capa_erp`).

El `downgrade` es de **mejor esfuerzo**, sólo para que la cadena se pueda bajar (lo recorre un test de otra
revisión): vuelve a marcar `store` a las ubicaciones que eran su propia sucursal y borra `branches`. No devuelve
las cajas reasignadas ni el dueño de los depósitos huérfanos. El camino de vuelta real es el respaldo previo al
deploy.
"""
import os

from alembic import op
from libracore.db.migraciones import conexion_libracore

from app.sucursales_migracion import migrar, parsear_mapa

revision = "0007_sucursales_jerarquicas"
down_revision = "0006_promociones"
branch_labels = None
depends_on = None


def upgrade():
    conn = conexion_libracore(op.get_bind())
    migrar(conn, depositos_a_sucursal=parsear_mapa(os.environ.get("VENTALIBRA_DEPOSITOS_A_SUCURSAL", "")))


def downgrade():
    conn = conexion_libracore(op.get_bind())
    conn.execute(
        "UPDATE locations SET location_type = 'store' "
        "WHERE id IN (SELECT id FROM branches WHERE default_location_id = id)"
    )
    conn.execute("UPDATE locations SET branch_id = NULL")
    conn.execute("DELETE FROM branches")
