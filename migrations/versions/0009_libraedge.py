"""libraedge: las tablas del nodo offline (LibraEdge, ADR-090).

Llama a las funciones del paquete en vez de re-expresar el DDL con `op.create_table(...)`, por el mismo motivo que la
baseline: la fuente de verdad es el DDL de LibraEdge, y re-escribirlo acá crearía **una segunda fuente que se
desincroniza en el primer cambio** del motor. Es la misma revisión que `0003_libraedge` de Restolibra.

**Se crean en toda instancia, sea nodo o no.** Un central que nunca corra offline igual las necesita: `node_identity`
para autenticar a los nodos que le pushean, `sync_inbox` para deduplicar operaciones repetidas y `sync_changelog` para
publicar la bajada. Crearlas sólo donde la instancia sea un nodo (`app.offline.nodo()`) dejaría el schema de unas
instancias distinto del de otras **en silencio**. Por eso esta revisión **no consulta** la identidad del nodo.

Es idempotente (`CREATE TABLE IF NOT EXISTS`): corre igual sobre una instancia viva que sobre una base vacía. El arranque
(`app/db.py::connect`) llama a las mismas dos funciones (`tests/test_schema_propio_congelado.py`).

> El trigger del changelog **no** se instala acá. Publicar una tabla al changelog es una decisión de aprovisionamiento
> del central —qué se espeja hacia qué nodo—, no parte del schema del producto (`libraedge-central nodo publicar`).
"""
from alembic import op
from libracore.db.migraciones import conexion_libracore
from libraedge.db.changelog import init_changelog_schema
from libraedge.db.schema import init_schema as init_edge_schema

revision = "0009_libraedge"
down_revision = "0008_backfill_cc_pago_id"
branch_labels = None
depends_on = None


def upgrade():
    # `conexion_libracore` envuelve el bind de Alembic en la conexión que espera el DDL de la familia: traduce los `?`,
    # el `INTEGER PRIMARY KEY AUTOINCREMENT` y saltea el `PRAGMA foreign_keys = ON` con el que arranca `init_schema()` de
    # LibraEdge, que contra PostgreSQL reventaría.
    conn = conexion_libracore(op.get_bind())
    init_edge_schema(conn)
    init_changelog_schema(conn)


def downgrade():
    # 🔴 Bajar esta revisión NO borra las tablas: el outbox puede tener operaciones que un nodo generó durante un corte y
    # todavía no confirmó, y no están en ningún otro lado. Las tablas quedan y volver a subir es idempotente (`CREATE
    # TABLE IF NOT EXISTS`). No levanta, a diferencia de `0003_libraedge` de Restolibra: la cadena tiene que poder bajar
    # por debajo de esta revisión para deshacer las anteriores (`tests/test_created_at_hora_ar.py` baja hasta la `0001`).
    pass
