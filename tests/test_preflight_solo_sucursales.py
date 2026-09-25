"""Control positivo y controles negativos del preflight, sin tocar VPS ni bases reales."""
import importlib.util
import sqlite3
from pathlib import Path

import pytest
from motor_de_test import TEST_DATABASE_URL

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "preflight_solo_sucursales.py"
spec = importlib.util.spec_from_file_location("preflight_solo_sucursales", SCRIPT)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "copia.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE locations (id INTEGER, name TEXT, location_type TEXT,
                                    active INTEGER, is_default INTEGER);
            CREATE TABLE stock_movements (location_id INTEGER, item_id INTEGER,
                                          variant_id INTEGER, quantity_delta NUMERIC);
            CREATE TABLE cajas (id INTEGER, sucursal_id INTEGER);
            CREATE TABLE turnos_caja (id INTEGER, caja_id INTEGER, estado TEXT);
            INSERT INTO locations VALUES (1, 'Depósito principal', 'warehouse', 1, 1);
            INSERT INTO locations VALUES (2, 'Salón', 'store', 1, 0);
            INSERT INTO cajas VALUES (1, 1);
            INSERT INTO stock_movements VALUES (1, 7, NULL, 5);
            INSERT INTO stock_movements VALUES (2, 7, NULL, 3);
        """)
    return path


def auditar(path, origen=1, destino=2):
    with preflight._abrir(sqlite_path=str(path), pg_url=None) as conn:
        return preflight.auditar(conn, origen, destino)


def test_preflight_positivo_y_solo_lectura(db):
    informe = auditar(db)
    assert informe["apto_para_planificar"] is True
    assert informe["bloqueos"] == []
    assert informe["cajas_historicas_origen"] == [1]
    assert [r["saldo"] for r in informe["stock"]] == ["5", "3"]
    with preflight._abrir(sqlite_path=str(db), pg_url=None) as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM locations")
    assert auditar(db)["origen"]["default"] is True


def test_turno_y_stock_negativo_bloquean_sin_cambiar_datos(db):
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO turnos_caja VALUES (10, 1, 'abierto')")
        conn.execute("INSERT INTO stock_movements VALUES (1, 9, NULL, -5)")
    informe = auditar(db)
    assert not informe["apto_para_planificar"]
    assert informe["turnos_abiertos_origen"] == [{"id": 10, "caja_id": 1}]
    assert informe["saldos_negativos_origen"][0]["saldo"] == "-5"
    assert len(informe["bloqueos"]) == 2
    assert auditar(db)["turnos_abiertos_origen"] == informe["turnos_abiertos_origen"]


def test_turno_destino_tambien_bloquea_migracion(db):
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO cajas VALUES (2, 2)")
        conn.execute("INSERT INTO turnos_caja VALUES (11, 2, 'abierto')")
    informe = auditar(db)
    assert informe["turnos_abiertos_destino"] == [{"id": 11, "caja_id": 2}]
    assert not informe["apto_para_planificar"]


@pytest.mark.parametrize("sql", [
    "UPDATE locations SET location_type='warehouse' WHERE id=2",
    "UPDATE locations SET active=0 WHERE id=2",
    "UPDATE locations SET is_default=0 WHERE id=1",
])
def test_tipo_estado_o_default_incorrectos_bloquean(db, sql):
    with sqlite3.connect(db) as conn:
        conn.execute(sql)
    assert not auditar(db)["apto_para_planificar"]


def test_origen_o_destino_inexistentes_bloquean(db):
    assert not auditar(db, destino=99)["apto_para_planificar"]
    assert not auditar(db, origen=99)["apto_para_planificar"]
    with pytest.raises(ValueError, match="distintos"):
        auditar(db, origen=1, destino=1)


def test_preflight_postgres_real_es_de_solo_lectura(admin_client):
    """Ejercita el driver de producción sobre la base local EXCLUSIVA de tests."""
    import psycopg

    origen_r = admin_client.post("/locations", json={
        "name": "Depósito test", "location_type": "warehouse",
    })
    assert origen_r.status_code == 200, origen_r.text
    # El escenario previo a la transición: el depósito es el predeterminado.
    hecho = admin_client.put(f"/locations/{origen_r.json()['id']}", json={
        "name": "Depósito test", "location_type": "warehouse", "is_default": True, "active": True,
    })
    assert hecho.status_code == 200, hecho.text
    origen = hecho.json()
    destino_r = admin_client.post("/locations", json={
        "name": "Salón test", "location_type": "store",
    })
    assert destino_r.status_code == 200, destino_r.text
    with preflight._abrir(sqlite_path=None, pg_url=TEST_DATABASE_URL) as conn:
        informe = preflight.auditar(conn, origen["id"], destino_r.json()["id"])
        assert informe["apto_para_planificar"] is True
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("DELETE FROM locations")
    assert len(admin_client.get("/locations").json()) == 3
