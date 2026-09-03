"""Baseline: las tablas propias de VentaLibra tal como ya existen.

Esta revisión **llama a `init_schema_propio()`** en vez de re-expresar sus
tablas en `op.create_table(...)`. Es la misma decisión que tomó la `0001` de
LibraCore y por el mismo motivo: la fuente de verdad es DDL crudo, y
re-escribirlo acá crearía **una segunda fuente que se desincroniza en el primer
cambio**.

Desde esta revisión, las seis `init_*_schema()` de `app/db.py` son de **sólo
lectura**: todo cambio de schema va como revisión nueva. Lo sostiene
`tests/test_schema_propio_congelado.py`, no la memoria de quien edite.

**Se puede correr sobre una instancia viva**, y es lo que se hace: las funciones
son idempotentes, así que `alembic upgrade head` sobre una base que ya tiene el
schema hace lo mismo que un arranque de la app, más registrar la versión. Por
eso las 2 instancias existentes **se migran, no se estampan**: el resultado es
el mismo y además queda verificado.

🔴 **Por qué llama a `init_commerce_schema()` primero.** Tres de las cinco
tablas propias tienen FK contra tablas de LibraCommerce: `party_billing` y
`party_roles` contra `parties`, y `sale_mp_orders` contra `sales`. Y
LibraCommerce **no tiene cadena de Alembic**: sus tablas nacen de
`init_schema()` al conectar, o sea *después* de que corren las migraciones. En
una instancia viva eso no se nota (las tablas están hace meses), pero en un alta
nueva las migraciones corren **antes del primer arranque** —ver
`libracore/provisioning/nuevo_cliente.py`— y sin esto la baseline moriría con
`relation "parties" does not exist`.

La alternativa era declarar esas FK condicionales, y es peor: dejaría el schema
de una instancia nueva **distinto** del de una vieja, en silencio. Llamar a la
función del motor —idempotente, y un no-op donde ya corrió— mantiene las dos
iguales. No es tomar posesión del schema de LibraCommerce: es declarar una
dependencia que existe.
"""
from alembic import op
from libracommerce.db.schema import init_schema as init_commerce_schema
from libracore.db.migraciones import conexion_libracore

from app.schema_propio import init_schema_propio

revision = "0001_baseline_ventalibra"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # `conexion_libracore` envuelve el bind de Alembic en la conexión que espera
    # el DDL de la familia: es la que traduce los `PRAGMA` de SQLite y las
    # excepciones de psycopg. Sin ella, el `PRAGMA foreign_keys = ON` con el que
    # arranca `init_schema()` de LibraCommerce revienta contra PostgreSQL.
    conn = conexion_libracore(op.get_bind())
    init_commerce_schema(conn)
    init_schema_propio(conn)


def downgrade():
    # Bajar de la baseline es borrar los usuarios del POS, la numeración de
    # comprobantes y las órdenes de MercadoPago. No hay caso de uso que lo
    # justifique y sí una forma muy barata de perder una instancia: el rollback
    # de esta revisión es restaurar el backup.
    raise NotImplementedError(
        "La baseline no se baja: para volver atrás, restaurar el backup de la "
        "instancia."
    )
