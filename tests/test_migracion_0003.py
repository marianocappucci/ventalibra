"""La revisión `0003_capa_erp`: `upgrade()` sobre un escenario con la forma de
los datos reales (ver F0 del plan post-P9, ADR-025), los invariantes, y
`downgrade()` restaurando exactamente lo que había.

No corre por `alembic upgrade`/`downgrade` como CLI: llama directamente a las
funciones `upgrade()`/`downgrade()` del módulo de la revisión, con `op` de
Alembic atado a la conexión de la suite (mismo patrón para probar una
revisión aislada sin tener que levantar toda la cadena). El schema de
partida (equivalente a la `0002`) sale de `app.db.connect()` +
`services.billing.configure()`, que son las funciones `init_*_schema()`
"congeladas" en esa forma -- exactamente lo que describe el propio
`schema_propio.py`.
"""
import importlib.util
import json
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from libracore.db import caja as db_caja
from libracore.db import clients as db_clients
from libracore.db.core import get_connection
from motor_de_test import TEST_DATABASE_URL

from app import db as app_db
from app.services import billing

_REVISION_PATH = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0003_capa_erp.py"


def _cargar_revision():
    spec = importlib.util.spec_from_file_location("_rev_0003_capa_erp", _REVISION_PATH)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def sqla_conn():
    """Una conexión SQLAlchemy sobre la MISMA base de test, con `op` de
    Alembic atado -- lo que las funciones `upgrade()`/`downgrade()` de la
    revisión necesitan (`from alembic import op; op.get_bind()`)."""
    from sqlalchemy import create_engine

    url = TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url)
    with engine.connect() as connection:
        ctx = MigrationContext.configure(connection)
        with Operations.context(ctx):
            yield connection
    engine.dispose()


@pytest.fixture
def escenario():
    """Arma el schema (equivalente a la revisión `0002`) y siembra el
    escenario de F0 del plan: ventas viejas con `occurred_on` NULL y
    `confirmed_at` UTC, un fiado duplicado (demo), un fiado sin pago (dev),
    un borrador abandonado, un proveedor que es party y un cliente cuyo id
    de LibraCore NO coincide con el de su party.

    Devuelve un dict con los ids que las aserciones necesitan.
    """
    conn = app_db.connect(TEST_DATABASE_URL)
    billing.configure(TEST_DATABASE_URL)
    # `billing.configure()` sólo corre `init_core_schema()` -- la baseline
    # CONGELADA de LibraCore. `ventas_pagos.recibido` lo agrega la migración
    # `0010` de ese motor: sin correr su cadena, una instancia real (que SÍ
    # la tiene aplicada) no está representada. `upgrade()` es idempotente
    # sobre lo que ya existe.
    from libracore.migrar import upgrade as _upgrade_libracore

    _upgrade_libracore(TEST_DATABASE_URL)

    # -- Catálogo mínimo, para el invariante de stock ------------------------
    conn.execute("INSERT INTO units (code, name) VALUES ('un', 'Unidad')")
    cur = conn.execute(
        "INSERT INTO catalog_items (item_type, name, unit_code) VALUES ('product', 'Yerba', 'un')"
    )
    item_id = cur.lastrowid
    # `app.db.connect()` ya sembró un depósito default (F3: lo necesita
    # `erp.stock`); un segundo `is_default=1` viola
    # `idx_locations_one_default` (UNIQUE parcial).
    location_id = conn.execute("SELECT id FROM locations WHERE is_default = 1 LIMIT 1").fetchone()[0]

    # -- Parties: dos clientes que fían y un proveedor -----------------------
    def _party(nombre, tipo="person"):
        cur = conn.execute(
            "INSERT INTO parties (party_type, display_name) VALUES (?, ?)", (tipo, nombre),
        )
        return cur.lastrowid

    party_demo = _party("Cliente Demo")   # fiado duplicado
    party_dev = _party("Cliente Dev")     # fiado sin pago
    party_proveedor = _party("Proveedor SRL", tipo="organization")
    # `party_nuevo`: rol customer pero SIN fila `clients` todavía -- el caso
    # real de un cliente dado de alta antes de que `CustomerService.create`
    # empezara a crearla de una (ver punto 1(a) del arreglo). El backfill del
    # paso 8 de la revisión tiene que crearle la suya.
    party_nuevo = _party("Cliente Nuevo Sin Cuenta Abierta")
    # `party_con_pago_post_upgrade`: mismo caso, pero DESPUÉS del upgrade se le
    # carga un cobro contra el `clients.id` que el backfill le creó -- para
    # probar que el downgrade NO borra un cliente con movimientos propios.
    party_con_pago_post_upgrade = _party("Cliente Con Pago Después De Migrar")
    for party_id in (party_demo, party_dev, party_nuevo, party_con_pago_post_upgrade):
        conn.execute(
            "INSERT INTO party_roles (party_id, role) VALUES (?, 'customer')", (party_id,),
        )
    conn.execute(
        "INSERT INTO party_roles (party_id, role) VALUES (?, 'supplier')", (party_proveedor,),
    )
    conn.commit()

    # -- Clientes de LibraCore, con ids que NO coinciden con su party --------
    # (mismo caso medido en ventalibra-dev: los clients 1/2/3 son otras
    # personas que sus parties homónimos). Se fuerza corriéndose el
    # autoincrement con un cliente de relleno primero.
    db_clients.resolver_cliente_externo("party-999999", "Relleno para desalinear ids")
    cliente_demo_id = db_clients.resolver_cliente_externo(
        f"party-{party_demo}", "Cliente Demo",
    )
    cliente_dev_id = db_clients.resolver_cliente_externo(
        f"party-{party_dev}", "Cliente Dev",
    )
    assert cliente_demo_id != party_demo
    assert cliente_dev_id != party_dev

    def _venta(numero, status, *, customer_party_id=None, occurred_on=None,
              confirmed_at=None, total=0, created_at=None):
        if created_at is not None:
            cur = conn.execute(
                "INSERT INTO sales (number, status, customer_party_id, occurred_on, "
                "confirmed_at, total, source_type, created_at) VALUES (?,?,?,?,?,?,'pos',?)",
                (numero, status, customer_party_id, occurred_on, confirmed_at, total, created_at),
            )
        else:
            cur = conn.execute(
                "INSERT INTO sales (number, status, customer_party_id, occurred_on, "
                "confirmed_at, total, source_type) VALUES (?,?,?,?,?,?,'pos')",
                (numero, status, customer_party_id, occurred_on, confirmed_at, total),
            )
        return cur.lastrowid

    # Venta vieja: occurred_on NULL, confirmed_at en UTC que cruza medianoche
    # AR (01:30 UTC del día 11 == 22:30 AR del día 10 -- exactamente el caso
    # que el arreglo del 2026-08-25 (ADR-016) existe para atrapar).
    venta_vieja = _venta(
        "POS-000001", "confirmed", occurred_on=None,
        confirmed_at="2026-08-11T01:30:00+00:00", total=1000,
    )
    conn.execute(
        "INSERT INTO stock_movements (item_id, location_id, movement_type, quantity_delta, "
        "occurred_at, source_type, source_id) VALUES (?,?,'sale',-2,'2026-08-10 22:30:00','sale',?)",
        (item_id, location_id, venta_vieja),
    )

    # Venta DEMO: fiada, con pago cuenta_corriente en sale_payments (via
    # `pagos[]`) Y su cc_debito -- el doble conteo.
    venta_demo = _venta(
        "POS-000002", "confirmed", customer_party_id=party_demo,
        occurred_on="2026-09-10", confirmed_at="2026-09-10T20:00:00+00:00", total=40800,
    )
    conn.execute(
        "INSERT INTO sale_payments (sale_id, method, amount, reference) VALUES (?,?,?,?)",
        (venta_demo, "cuenta_corriente", 40800, f"sale-{venta_demo}-cuenta_corriente"),
    )
    debito_demo_id = db_clients_create_cc_debito(
        cliente_demo_id, 40800, "2026-09-10", concepto="Venta POS-000002",
        referencia=f"sale-{venta_demo}-cuenta_corriente",
    )

    # Venta DEV: fiada por el camino `medio_pago` suelto -- NUNCA generó fila
    # en `sale_payments` (ver docstring de la revisión). El débito directo
    # queda como estaba.
    venta_dev = _venta(
        "POS-000003", "confirmed", customer_party_id=party_dev,
        occurred_on="2026-09-05", confirmed_at="2026-09-05T18:00:00+00:00", total=18000,
    )
    debito_dev_id = db_clients_create_cc_debito(
        cliente_dev_id, 18000, "2026-09-05", concepto="Venta POS-000003",
        referencia=f"sale-{venta_dev}",
    )

    # Movimiento de caja de la venta vieja (efectivo, con turno y factura) --
    # lo que `venta_links.turno_id`/`factura_id` tienen que reconstruir.
    factura_id = _crear_factura_minima(conn)
    turno_id = _crear_turno_minimo(conn)
    db_caja.create_caja_movimiento(
        "2026-08-10", "ingreso", "Venta POS-000001", 1000,
        referencia=f"sale-{venta_vieja}-efectivo", medio_pago="efectivo",
        factura_id=factura_id, turno_id=turno_id,
    )

    # Borrador abandonado: `created_at` de hace tres días.
    venta_borrador = _venta(
        "POS-000004", "draft", created_at="2026-09-01 10:00:00",
    )

    conn.commit()

    return {
        "conn": conn,
        "item_id": item_id, "location_id": location_id,
        "party_demo": party_demo, "party_dev": party_dev, "party_proveedor": party_proveedor,
        "party_nuevo": party_nuevo, "party_con_pago_post_upgrade": party_con_pago_post_upgrade,
        "cliente_demo_id": cliente_demo_id, "cliente_dev_id": cliente_dev_id,
        "venta_vieja": venta_vieja, "venta_demo": venta_demo, "venta_dev": venta_dev,
        "venta_borrador": venta_borrador,
        "debito_demo_id": debito_demo_id, "debito_dev_id": debito_dev_id,
        "turno_id": turno_id, "factura_id": factura_id,
    }


def db_clients_create_cc_debito(cliente_id, monto, fecha, *, concepto, referencia):
    from libracore.db.cuenta_corriente import create_cc_debito

    return create_cc_debito(cliente_id, monto, fecha, concepto=concepto, referencia=referencia)


def _crear_factura_minima(conn) -> int:
    with get_connection() as c:
        cur = c.execute(
            "INSERT INTO facturas (tipo, punto_venta, numero, fecha, items, subtotal, "
            "iva_amount, total) VALUES (11, 1, 1, '2026-08-10', '[]', 826.45, 173.55, 1000)"
        )
        c.commit()
        return cur.lastrowid


def _crear_turno_minimo(conn) -> int:
    with get_connection() as c:
        c.execute(
            "INSERT INTO usuarios (username, nombre, password_hash, role) "
            "VALUES ('cajera', 'Cajera', 'x', 'admin') ON CONFLICT (username) DO NOTHING"
        )
        row = c.execute("SELECT id FROM usuarios WHERE username='cajera'").fetchone()
        usuario_id = row[0]
        cur = c.execute(
            "INSERT INTO turnos_caja (usuario_id, apertura, monto_inicial, estado) "
            "VALUES (?, '2026-08-10 08:00:00', 0, 'abierto')",
            (usuario_id,),
        )
        c.commit()
        return cur.lastrowid


# ── Invariantes ──────────────────────────────────────────────────────────


def _snapshot(conn) -> dict:
    """Lo que tiene que dar igual antes de `upgrade()` y después de
    `downgrade()`."""
    ventas = {
        r[0]: (r[1], round(float(r[2] or 0), 2))
        for r in conn.execute("SELECT status, COUNT(*), SUM(total) FROM sales GROUP BY status").fetchall()
    }
    pagos_sale_payments = {
        r[0]: round(float(r[1]), 2)
        for r in conn.execute("SELECT method, SUM(amount) FROM sale_payments GROUP BY method").fetchall()
    }
    stock = {
        (r[0], r[1]): round(float(r[2]), 3)
        for r in conn.execute(
            "SELECT item_id, location_id, SUM(quantity_delta) FROM stock_movements "
            "GROUP BY item_id, location_id"
        ).fetchall()
    }
    caja = {
        r[0]: round(float(r[1]), 2)
        for r in conn.execute("SELECT tipo, SUM(monto) FROM caja_movimientos GROUP BY tipo").fetchall()
    }
    return {"ventas": ventas, "pagos": pagos_sale_payments, "stock": stock, "caja": caja}


def _saldo_manual(conn, cliente_id: int) -> float:
    """El saldo de cuenta corriente de un cliente, calculado a mano con la
    MISMA lógica que usa el origen `VENTAS_LIBRACOMMERCE_POR_EXTERNAL_REF`
    de libracore v1.100.0 (D3, ADR-025): llama a la función real -- el punto
    4 de la especificación de F3 ya no está diferido, el pin lo trae.
    """
    from libracore.db.cuenta_corriente import (
        VENTAS_LIBRACOMMERCE_POR_EXTERNAL_REF,
        get_cc_saldo,
    )

    return round(float(get_cc_saldo(cliente_id, origen=VENTAS_LIBRACOMMERCE_POR_EXTERNAL_REF)), 2)


def test_upgrade_invariantes_downgrade(escenario, sqla_conn):
    conn = escenario["conn"]
    modulo = _cargar_revision()

    antes = _snapshot(conn)
    # El saldo "de hoy" es exactamente lo que ya suma `get_cc_saldo` con el
    # origen default (`cc_debitos` - `cc_pagos`; `ventas_pagos` no cuenta
    # porque la venta vive en `sales`, no en la `ventas` legada).
    saldo_demo_antes = conn.execute(
        "SELECT COALESCE(SUM(monto),0) FROM cc_debitos WHERE cliente_id=?",
        (escenario["cliente_demo_id"],),
    ).fetchone()[0]
    saldo_dev_antes = conn.execute(
        "SELECT COALESCE(SUM(monto),0) FROM cc_debitos WHERE cliente_id=?",
        (escenario["cliente_dev_id"],),
    ).fetchone()[0]
    assert round(float(saldo_demo_antes), 2) == 40800.0
    assert round(float(saldo_dev_antes), 2) == 18000.0

    proveedor_antes = dict(conn.execute(
        "SELECT party_id, role FROM party_roles WHERE party_id=?",
        (escenario["party_proveedor"],),
    ).fetchone() or {})
    # 🔴 `conn` (la del dominio) no puede quedar con una transacción abierta
    # mientras `sqla_conn` corre la migración: un `ALTER TABLE` necesita lock
    # exclusivo y una lectura sin confirmar en `conn` --aunque sea de otra
    # tabla-- lo deja esperando para siempre (medido: colgó 10+ minutos).
    conn.commit()

    # ── upgrade() ──────────────────────────────────────────────────────
    # `modulo.upgrade()` escribe por `op.get_bind()` (la conexión SQLAlchemy
    # de `sqla_conn`), NO por `conn` (la del dominio, otra conexión física a
    # la misma base) -- hay que confirmarla explícitamente para que `conn` la
    # vea en su próxima consulta (READ COMMITTED: ve lo último confirmado).
    modulo.upgrade()
    sqla_conn.commit()

    # 1. Venta vieja: occurred_on completado con la fecha LOCAL (cruza el
    #    día respecto de la fecha UTC de confirmed_at).
    fila = conn.execute(
        "SELECT occurred_on FROM sales WHERE id=?", (escenario["venta_vieja"],),
    ).fetchone()
    assert fila[0] == "2026-08-10"

    # 2. sale_payments -> ventas_pagos (recibido va NULL: no vino en el pago viejo).
    copiados = conn.execute(
        "SELECT medio, monto, estado, recibido FROM ventas_pagos WHERE venta_id=?",
        (escenario["venta_demo"],),
    ).fetchall()
    assert [tuple(r) for r in copiados] == [("cuenta_corriente", 40800.0, "aprobado", None)]

    # 3. venta_links: turno_id/factura_id reconstruidos desde caja_movimientos.
    link = conn.execute(
        "SELECT turno_id, factura_id FROM venta_links WHERE venta_id=?",
        (escenario["venta_vieja"],),
    ).fetchone()
    assert tuple(link) == (escenario["turno_id"], escenario["factura_id"])

    # 4. Borrador abandonado -> cancelado.
    borrador = conn.execute(
        "SELECT status, status_detail FROM sales WHERE id=?", (escenario["venta_borrador"],),
    ).fetchone()
    assert tuple(borrador) == ("cancelled", "borrador_descartado")

    # 5. El doble conteo: el débito de demo (duplicado) desaparece; el de
    #    dev (sin pago que lo acompañe) queda igual.
    assert conn.execute(
        "SELECT 1 FROM cc_debitos WHERE id=?", (escenario["debito_demo_id"],),
    ).fetchone() is None
    assert conn.execute(
        "SELECT monto FROM cc_debitos WHERE id=?", (escenario["debito_dev_id"],),
    ).fetchone()[0] == 18000.0

    # 6. El invariante que atrapa el doble conteo: el saldo de cada cliente,
    #    calculado con la lógica del origen nuevo, da lo mismo que daba antes.
    assert _saldo_manual(conn, escenario["cliente_demo_id"]) == round(float(saldo_demo_antes), 2)
    assert _saldo_manual(conn, escenario["cliente_dev_id"]) == round(float(saldo_dev_antes), 2)

    # 7. Lo que NO tiene que tocarse: el proveedor sigue siendo party+role,
    #    y el stock/caja no se movieron.
    proveedor_despues = dict(conn.execute(
        "SELECT party_id, role FROM party_roles WHERE party_id=?",
        (escenario["party_proveedor"],),
    ).fetchone() or {})
    assert proveedor_despues == proveedor_antes

    # 8. Backfill: un party con rol customer que no tenía fila `clients` la
    #    tiene ahora, enlazada por external_ref.
    cliente_nuevo = conn.execute(
        "SELECT id, name FROM clients WHERE external_ref = ?",
        (f"party-{escenario['party_nuevo']}",),
    ).fetchone()
    assert cliente_nuevo is not None
    assert cliente_nuevo[1] == "Cliente Nuevo Sin Cuenta Abierta"

    cliente_pago_post = conn.execute(
        "SELECT id FROM clients WHERE external_ref = ?",
        (f"party-{escenario['party_con_pago_post_upgrade']}",),
    ).fetchone()
    assert cliente_pago_post is not None
    cliente_pago_post_id = cliente_pago_post[0]

    # Los que YA tenían su fila antes del upgrade (creada en el fixture, como
    # lo hace `CustomerService.create` desde el punto 1(a) del arreglo) no se
    # duplican ni cambian de id.
    assert conn.execute(
        "SELECT id FROM clients WHERE external_ref = ?", (f"party-{escenario['party_demo']}",),
    ).fetchone()[0] == escenario["cliente_demo_id"]
    assert conn.execute(
        "SELECT id FROM clients WHERE external_ref = ?", (f"party-{escenario['party_dev']}",),
    ).fetchone()[0] == escenario["cliente_dev_id"]

    # Simula un cobro real cargado DESPUÉS del upgrade contra el cliente que
    # el backfill acaba de crear -- el downgrade no puede llevárselo puesto.
    conn.execute(
        "INSERT INTO cc_pagos (cliente_id, monto, fecha, concepto, referencia, medio_pago) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (cliente_pago_post_id, 500, "2026-09-14", "Pago después de migrar", "", "efectivo"),
    )
    conn.commit()

    despues = _snapshot(conn)
    assert despues["stock"] == antes["stock"]
    assert despues["caja"] == antes["caja"]
    assert despues["pagos"] == antes["pagos"]  # sale_payments nunca se toca
    conn.commit()  # ídem: liberar antes de que sqla_conn ALTER TABLE la FK.

    # ── downgrade() ────────────────────────────────────────────────────
    modulo.downgrade()
    sqla_conn.commit()

    # 🔴 `venta_links` y la FK repuntada NO desaparecen: `services/billing.py
    # ::configure()` los asegura en CADA arranque (idéntico patrón a
    # `app/database.py::init_db()` de Contalibra/Restolibra), y el fixture
    # `escenario` ya llamó a `configure()` antes de que `upgrade()` corriera
    # -- así que en esta base los creó el arranque, no esta migración, y el
    # `downgrade()` de los datos no les toca la baseline de schema. Ver el
    # docstring de `configure()`.
    assert conn.execute(
        "SELECT to_regclass('venta_links')"
    ).fetchone()[0] is not None
    assert conn.execute(
        "SELECT to_regclass('_migracion_0003')"
    ).fetchone()[0] is None

    fila = conn.execute(
        "SELECT occurred_on FROM sales WHERE id=?", (escenario["venta_vieja"],),
    ).fetchone()
    assert fila[0] is None

    borrador = conn.execute(
        "SELECT status, status_detail FROM sales WHERE id=?", (escenario["venta_borrador"],),
    ).fetchone()
    assert tuple(borrador) == ("draft", None)

    # 8. Backfill deshecho, salvo el cliente con movimientos propios cargados
    #    después del upgrade: ESE no se borra -- se perdería un cobro real.
    assert conn.execute(
        "SELECT 1 FROM clients WHERE external_ref = ?", (f"party-{escenario['party_nuevo']}",),
    ).fetchone() is None
    assert conn.execute(
        "SELECT 1 FROM clients WHERE id = ?", (cliente_pago_post_id,),
    ).fetchone() is not None
    # Los que ya existían antes del upgrade (demo/dev) no los toca esta acción
    # -- no hay bookkeeping de backfill para ellos.
    assert conn.execute(
        "SELECT 1 FROM clients WHERE external_ref = ?", (f"party-{escenario['party_demo']}",),
    ).fetchone() is not None
    assert conn.execute(
        "SELECT 1 FROM clients WHERE external_ref = ?", (f"party-{escenario['party_dev']}",),
    ).fetchone() is not None

    assert tuple(conn.execute(
        "SELECT monto, referencia FROM cc_debitos WHERE id=?", (escenario["debito_demo_id"],),
    ).fetchone()) == (40800.0, f"sale-{escenario['venta_demo']}-cuenta_corriente")

    assert conn.execute(
        "SELECT COUNT(*) FROM ventas_pagos WHERE venta_id=?", (escenario["venta_demo"],),
    ).fetchone()[0] == 0

    # La FK sigue apuntando a `sales(id)` -- por la misma razón de arriba,
    # no la revierte esta migración en esta base.
    fk = conn.execute("""
        SELECT pg_get_constraintdef(oid) FROM pg_constraint
        WHERE conrelid = 'ventas_pagos'::regclass AND contype='f'
    """).fetchall()
    assert any("REFERENCES sales(" in f[0] for f in fk)

    final = _snapshot(conn)
    assert final == antes


def test_upgrade_es_idempotente(escenario, sqla_conn):
    """Correr `upgrade()` DOS veces tiene que dar exactamente lo mismo que
    correrlo una sola vez: es la garantía que permite invocarlo a mano para
    recuperar un estado a medio migrar (ver "Idempotencia" en el docstring
    de la revisión, y el incidente de LibraDesk que documenta por qué hace
    falta) -- si no fuera cierta, la segunda corrida podría duplicar trabajo
    o, peor, dejar la bitácora de `downgrade()` sin sentido."""
    conn = escenario["conn"]
    modulo = _cargar_revision()

    antes = _snapshot(conn)
    saldo_demo_antes = conn.execute(
        "SELECT COALESCE(SUM(monto),0) FROM cc_debitos WHERE cliente_id=?",
        (escenario["cliente_demo_id"],),
    ).fetchone()[0]
    saldo_dev_antes = conn.execute(
        "SELECT COALESCE(SUM(monto),0) FROM cc_debitos WHERE cliente_id=?",
        (escenario["cliente_dev_id"],),
    ).fetchone()[0]
    conn.commit()

    modulo.upgrade()
    sqla_conn.commit()
    bitacora_tras_1 = conn.execute(
        "SELECT accion, referencia_id FROM _migracion_0003 ORDER BY accion, referencia_id, id"
    ).fetchall()

    # Segunda corrida: el caso real es un operador recuperando un estado a
    # medio migrar invocando `upgrade()` a mano, no un reintento automático.
    modulo.upgrade()
    sqla_conn.commit()

    # (b) Ninguna acción quedó registrada dos veces para la misma referencia.
    bitacora_tras_2 = conn.execute(
        "SELECT accion, referencia_id FROM _migracion_0003 ORDER BY accion, referencia_id, id"
    ).fetchall()
    assert [tuple(f) for f in bitacora_tras_2] == [tuple(f) for f in bitacora_tras_1]

    # (a) Mismo estado que si hubiera corrido una sola vez -- ventas, pagos,
    # venta_links, cc_debitos, clients, saldos por cliente.
    fila = conn.execute(
        "SELECT occurred_on FROM sales WHERE id=?", (escenario["venta_vieja"],),
    ).fetchone()
    assert fila[0] == "2026-08-10"

    copiados = conn.execute(
        "SELECT medio, monto, estado, recibido FROM ventas_pagos WHERE venta_id=?",
        (escenario["venta_demo"],),
    ).fetchall()
    assert [tuple(r) for r in copiados] == [("cuenta_corriente", 40800.0, "aprobado", None)]

    link = conn.execute(
        "SELECT turno_id, factura_id FROM venta_links WHERE venta_id=?",
        (escenario["venta_vieja"],),
    ).fetchone()
    assert tuple(link) == (escenario["turno_id"], escenario["factura_id"])

    assert conn.execute(
        "SELECT 1 FROM cc_debitos WHERE id=?", (escenario["debito_demo_id"],),
    ).fetchone() is None
    assert conn.execute(
        "SELECT monto FROM cc_debitos WHERE id=?", (escenario["debito_dev_id"],),
    ).fetchone()[0] == 18000.0

    assert _saldo_manual(conn, escenario["cliente_demo_id"]) == round(float(saldo_demo_antes), 2)
    assert _saldo_manual(conn, escenario["cliente_dev_id"]) == round(float(saldo_dev_antes), 2)

    assert conn.execute(
        "SELECT 1 FROM clients WHERE external_ref = ?", (f"party-{escenario['party_nuevo']}",),
    ).fetchone() is not None

    despues = _snapshot(conn)
    assert despues["stock"] == antes["stock"]
    assert despues["caja"] == antes["caja"]
    assert despues["pagos"] == antes["pagos"]
    conn.commit()

    # (c) Un downgrade() después de las DOS corridas restaura el estado
    # original -- una sola vez, deshaciendo lo que dice la bitácora, sin
    # importar cuántas corridas de upgrade() la escribieron.
    modulo.downgrade()
    sqla_conn.commit()

    fila = conn.execute(
        "SELECT occurred_on FROM sales WHERE id=?", (escenario["venta_vieja"],),
    ).fetchone()
    assert fila[0] is None

    borrador = conn.execute(
        "SELECT status, status_detail FROM sales WHERE id=?", (escenario["venta_borrador"],),
    ).fetchone()
    assert tuple(borrador) == ("draft", None)

    assert tuple(conn.execute(
        "SELECT monto, referencia FROM cc_debitos WHERE id=?", (escenario["debito_demo_id"],),
    ).fetchone()) == (40800.0, f"sale-{escenario['venta_demo']}-cuenta_corriente")

    assert conn.execute(
        "SELECT COUNT(*) FROM ventas_pagos WHERE venta_id=?", (escenario["venta_demo"],),
    ).fetchone()[0] == 0

    assert conn.execute(
        "SELECT 1 FROM clients WHERE external_ref = ?", (f"party-{escenario['party_nuevo']}",),
    ).fetchone() is None

    final = _snapshot(conn)
    assert final == antes


def test_downgrade_sin_upgrade_no_falla(escenario, sqla_conn):
    """Si `upgrade()` nunca corrió sobre esta base, `downgrade()` no tiene
    nada que deshacer -- y no debe reventar buscando `_migracion_0003`."""
    modulo = _cargar_revision()
    modulo.downgrade()  # no debe lanzar
