"""cliente_lista_precio: la lista de precios asignada a un cliente.

Pegamento entre `clients` (LibraCore) y `price_lists` (LibraCommerce), del
motor desde el 2026-09-28 (ADR-010 de libracommerce, extraído del add-on
mayorista de Contalibra: `erp.schema.crear_cliente_lista_precio`, mismo
criterio que `crear_venta_links`). VentaLibra no tenía este enganche —no tiene
el add-on `mayorista`, y "lista de precios" es un módulo siempre libre desde
la fase 7— pero sí tiene listas de precio (`build_listas_precio_router`) desde
ese mismo módulo, y la ficha del cliente del kit (`ClienteDetalle`, prop
`conListaDePrecio`) ya traía la card lista para asignarlas.

Llamada por esta revisión y por `app/services/billing.py::configure()` — la
MISMA función en las dos puntas, mismo criterio que `crear_venta_links` en ese
archivo, para que una instancia nueva (nace de la cadena) y una vieja (nació
del arranque) no diverjan.

🔴 Corre DESPUÉS de la cadena de LibraCore (crea `clients`) y de
`libracommerce.db.schema.init_schema()` (crea `price_lists`, aplicado por
`db.connect()` en cada arranque, y por la `0003_capa_erp` en el deploy): las
dos FK necesitan sus tablas destino. `libracore-migrar` va antes que esta
cadena en la declaración de `migraciones`, así que ya existen cuando corre
esta revisión.
"""
from alembic import op
from libracommerce.erp.schema import crear_cliente_lista_precio
from libracore.db.migraciones import conexion_libracore

revision = "0005_cliente_lista_precio"
down_revision = "0004_personas_del_motor"
branch_labels = None
depends_on = None


def upgrade():
    # `conexion_libracore` envuelve el bind de Alembic en la conexión de la
    # familia (traduce PRAGMA y excepciones), mismo criterio que el resto de
    # la cadena.
    conn = conexion_libracore(op.get_bind())
    crear_cliente_lista_precio(conn)


def downgrade():
    op.drop_table("cliente_lista_precio")
