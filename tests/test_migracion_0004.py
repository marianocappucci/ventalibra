"""La revisión `0004_personas_del_motor`: `upgrade()` sobre un escenario con la forma
de los datos reales de dev (clients 1/2/3 = parties 2/3/4, un proveedor sólo en `parties`), los
invariantes, y `downgrade()` devolviendo los ids originales.

Mismo patrón que `test_migracion_0003.py`: se llama directo a `upgrade()`/`downgrade()` del
módulo de la revisión, con `op` de Alembic atado a la conexión de la suite.
"""
import importlib.util
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from libracore.db import clients as db_clients
from libracore.db.core import get_connection
from motor_de_test import TEST_DATABASE_URL

from app import db as app_db
from app.services import billing

_REVISION_PATH = (
    Path(__file__).resolve().parent.parent / "migrations" / "versions"
    / "0004_personas_del_motor.py"
)


def _cargar_revision():
    spec = importlib.util.spec_from_file_location("_rev_0004_personas", _REVISION_PATH)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def sqla_conn():
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
    """El estado de VentaLibra antes de la `0004`, con la forma de dev.

    Parties: 1 proveedor, 3 clientes (A, B, C), 1 huérfano. Los `clients` NO coinciden con sus
    parties: A (party 2) es el client 3 y B (party 3) es el client 2 -- **un cruce**, que sólo
    sale bien si la renumeración pasa por un espacio temporal. C no tiene client todavía y, cuando
    la migración se lo cree, va a tener el id 5, que es el del party huérfano: el huérfano tiene
    que correrse.
    """
    conn = app_db.connect(TEST_DATABASE_URL)
    billing.configure(TEST_DATABASE_URL)
    from libracore.migrar import upgrade as _upgrade_libracore

    _upgrade_libracore(TEST_DATABASE_URL)

    def _party(nombre, tipo="person", activo=1, tax_id=None):
        cur = conn.execute(
            "INSERT INTO parties (party_type, display_name, tax_id, active) VALUES (?, ?, ?, ?)",
            (tipo, nombre, tax_id, activo),
        )
        return cur.lastrowid

    proveedor = _party("Proveedor SRL", "organization", tax_id="30-70000000-1")
    party_a = _party("Cliente A")
    party_b = _party("Cliente B")
    party_c = _party("Cliente C (inactivo)", activo=0)
    huerfano = _party("Sin rol")
    assert (proveedor, party_a, party_b, party_c, huerfano) == (1, 2, 3, 4, 5)
    conn.execute("INSERT INTO party_roles (party_id, role) VALUES (?, 'supplier')", (proveedor,))
    for p in (party_a, party_b, party_c):
        conn.execute("INSERT INTO party_roles (party_id, role) VALUES (?, 'customer')", (p,))
    conn.execute(
        "INSERT INTO party_billing (party_id, cuit, condicion_iva) VALUES (?, ?, ?)",
        (party_a, "30-11111111-1", "Responsable Inscripto"),
    )
    conn.commit()

    # Clients con ids desalineados y cruzados.
    db_clients.resolver_cliente_externo("party-999999", "Relleno 1")                 # client 1
    cliente_b = db_clients.resolver_cliente_externo(f"party-{party_b}", "Cliente B")  # client 2
    cliente_a = db_clients.resolver_cliente_externo(f"party-{party_a}", "Cliente A")  # client 3
    db_clients.resolver_cliente_externo("party-999998", "Relleno 2")                 # client 4
    assert (cliente_b, cliente_a) == (2, 3)

    # Ventas y compras que apuntan a los parties viejos.
    def _venta(numero, party_id, total):
        cur = conn.execute(
            "INSERT INTO sales (number, status, customer_party_id, total) VALUES (?, 'confirmed', ?, ?)",
            (numero, party_id, total),
        )
        return cur.lastrowid

    venta_a = _venta("POS-000001", party_a, 1000)
    venta_b = _venta("POS-000002", party_b, 2500)
    venta_sin = _venta("POS-000003", None, 300)
    orden = conn.execute(
        "INSERT INTO purchase_orders (number, supplier_party_id) VALUES ('OC-1', ?)", (proveedor,),
    ).lastrowid
    recepcion = conn.execute(
        "INSERT INTO purchase_receipts (supplier_party_id) VALUES (?)", (proveedor,),
    ).lastrowid

    # Cuenta corriente del client A (por su id de LibraCore): no se puede mover.
    with get_connection() as cx:
        cx.execute(
            "INSERT INTO cc_debitos (cliente_id, monto, fecha, concepto, referencia) "
            "VALUES (?, 500, '2026-09-10', 'venta', 'sale-1')", (cliente_a,),
        )
    conn.commit()
    return {
        "conn": conn, "proveedor": proveedor, "a": party_a, "b": party_b, "c": party_c,
        "huerfano": huerfano, "cliente_a": cliente_a, "cliente_b": cliente_b,
        "venta_a": venta_a, "venta_b": venta_b, "venta_sin": venta_sin,
        "orden": orden, "recepcion": recepcion,
    }


def _ids_de_parties(conn) -> dict[str, int]:
    return {n: int(i) for i, n in conn.execute("SELECT id, display_name FROM parties").fetchall()}


def test_upgrade_deja_cada_party_con_el_id_del_motor(escenario, sqla_conn):
    conn = escenario["conn"]
    _cargar_revision().upgrade()
    conn.commit()

    ids = _ids_de_parties(conn)
    # Cliente = party de igual id (el cruce 2<->3 se resolvió); C recibió el client nuevo 5.
    assert ids["Cliente A"] == escenario["cliente_a"] == 3
    assert ids["Cliente B"] == escenario["cliente_b"] == 2
    assert ids["Cliente C (inactivo)"] == 5
    # Proveedor = party con id + 100.000.
    prov_id = conn.execute("SELECT id FROM proveedores WHERE nombre = 'Proveedor SRL'").fetchone()[0]
    assert ids["Proveedor SRL"] == 100_000 + prov_id
    # El huérfano chocaba con el 5 de C: se corrió.
    assert ids["Sin rol"] == 200_005
    assert sorted(ids.values()) == sorted([3, 2, 5, 100_000 + prov_id, 200_005])


def test_upgrade_repunta_todo_lo_que_apunta_a_los_parties(escenario, sqla_conn):
    conn = escenario["conn"]
    _cargar_revision().upgrade()
    conn.commit()

    ventas = dict(conn.execute("SELECT number, customer_party_id FROM sales").fetchall())
    assert ventas == {"POS-000001": 3, "POS-000002": 2, "POS-000003": None}
    prov_party = conn.execute(
        "SELECT id FROM parties WHERE display_name = 'Proveedor SRL'"
    ).fetchone()[0]
    assert conn.execute("SELECT supplier_party_id FROM purchase_orders").fetchone()[0] == prov_party
    assert conn.execute("SELECT supplier_party_id FROM purchase_receipts").fetchone()[0] == prov_party
    assert conn.execute("SELECT party_id FROM party_billing").fetchone()[0] == 3
    roles = sorted(tuple(r) for r in conn.execute("SELECT party_id, role FROM party_roles").fetchall())
    assert roles == sorted([(3, "customer"), (2, "customer"), (5, "customer"), (prov_party, "supplier")])
    # Las FK siguen ahí: no se puede apuntar a un party que no existe.
    with pytest.raises(Exception, match="foreign key|violates"):
        conn.execute("UPDATE sales SET customer_party_id = 987654 WHERE number = 'POS-000001'")
        conn.commit()
    conn.rollback()


def test_upgrade_completa_el_cliente_del_motor_sin_pisar_lo_que_hay(escenario, sqla_conn):
    conn = escenario["conn"]
    _cargar_revision().upgrade()
    conn.commit()

    a = conn.execute("SELECT cuit_dni, iva_condition, activo FROM clients WHERE id = 3").fetchone()
    assert tuple(a) == ("30-11111111-1", "Responsable Inscripto", 1)     # completado desde party_billing
    c = conn.execute("SELECT name, activo, external_ref FROM clients WHERE id = 5").fetchone()
    assert tuple(c) == ("Cliente C (inactivo)", 0, f"party-{escenario['c']}")  # creado, y dado de baja
    prov = conn.execute("SELECT cuit_dni FROM proveedores").fetchone()[0]
    assert prov == "30-70000000-1"


def test_invariantes_ventas_compras_y_cuenta_corriente(escenario, sqla_conn):
    conn = escenario["conn"]
    antes_ventas = conn.execute("SELECT COUNT(*), SUM(total) FROM sales").fetchone()
    antes_cc = conn.execute("SELECT cliente_id, SUM(monto) FROM cc_debitos GROUP BY 1").fetchall()
    # La migración suelta y recrea FK (ACCESS EXCLUSIVE): corre con la app parada, así que acá
    # la lectura previa no puede dejar una transacción abierta que la bloquee.
    conn.commit()

    _cargar_revision().upgrade()
    conn.commit()

    assert tuple(conn.execute("SELECT COUNT(*), SUM(total) FROM sales").fetchone()) == tuple(antes_ventas)
    assert conn.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM purchase_receipts").fetchone()[0] == 1
    # `cc_*` no se toca: el saldo de cada client da igual.
    assert [tuple(r) for r in conn.execute(
        "SELECT cliente_id, SUM(monto) FROM cc_debitos GROUP BY 1").fetchall()] == [tuple(r) for r in antes_cc]


def test_upgrade_es_idempotente(escenario, sqla_conn):
    conn = escenario["conn"]
    rev = _cargar_revision()
    rev.upgrade()
    conn.commit()
    despues = _ids_de_parties(conn)
    proveedores = conn.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0]
    rev.upgrade()
    conn.commit()
    assert _ids_de_parties(conn) == despues
    assert conn.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0] == proveedores


def test_downgrade_devuelve_los_ids_originales(escenario, sqla_conn):
    conn = escenario["conn"]
    rev = _cargar_revision()
    rev.upgrade()
    conn.commit()
    rev.downgrade()
    conn.commit()

    assert _ids_de_parties(conn) == {
        "Proveedor SRL": 1, "Cliente A": 2, "Cliente B": 3, "Cliente C (inactivo)": 4, "Sin rol": 5,
    }
    ventas = dict(conn.execute("SELECT number, customer_party_id FROM sales").fetchall())
    assert ventas == {"POS-000001": 2, "POS-000002": 3, "POS-000003": None}
    assert conn.execute("SELECT supplier_party_id FROM purchase_orders").fetchone()[0] == 1
    # Lo que la migración creó se va; el cliente A vuelve a su forma original.
    assert conn.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM clients WHERE id = 5").fetchone()[0] == 0
    assert tuple(conn.execute("SELECT cuit_dni FROM clients WHERE id = 3").fetchone()) == ("",)
    assert conn.execute("SELECT to_regclass('_migracion_0004') IS NULL").fetchone()[0]


def test_un_party_cliente_y_proveedor_a_la_vez_frena_la_migracion(escenario, sqla_conn):
    conn = escenario["conn"]
    conn.execute("INSERT INTO party_roles (party_id, role) VALUES (?, 'customer')", (escenario["proveedor"],))
    conn.commit()
    with pytest.raises(RuntimeError, match="cliente y proveedor a la vez"):
        _cargar_revision().upgrade()
    conn.rollback()
    # No se tocó nada.
    assert _ids_de_parties(conn)["Cliente A"] == 2


def test_con_la_app_conectada_se_rinde_rapido_y_no_cambia_nada(escenario, sqla_conn):
    """Pasó en la demo (2026-09-26): la app vieja deja una conexión `idle in transaction` y el
    `ALTER TABLE` esperó casi 9 minutos, encolando las demás consultas. Ahora se rinde a los
    `LOCK_TIMEOUT` con un mensaje que dice qué hacer, y la transacción se revierte entera."""
    import psycopg

    conn = escenario["conn"]
    rev = _cargar_revision()
    rev.LOCK_TIMEOUT = "300ms"
    antes = _ids_de_parties(conn)
    conn.commit()

    otra_app = psycopg.connect(TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1))
    try:
        otra_app.execute("SELECT count(*) FROM sales")  # transacción abierta: lock de lectura
        with pytest.raises(RuntimeError, match="app PARADA"):
            rev.upgrade()
    finally:
        otra_app.close()
    # Alembic abortaría el proceso; acá se limpia la transacción fallida de la conexión del bind.
    sqla_conn.connection.driver_connection.rollback()

    # Nada cambió: ni ids, ni proveedores creados, ni bitácora.
    assert _ids_de_parties(conn) == antes
    assert conn.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0] == 0
    assert conn.execute("SELECT to_regclass('_migracion_0004') IS NULL").fetchone()[0]
    conn.commit()

    # Con la app parada, la misma migración corre.
    rev.upgrade()
    conn.commit()
    assert _ids_de_parties(conn)["Cliente A"] == escenario["cliente_a"]
