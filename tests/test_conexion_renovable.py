"""La conexión única del dominio sobrevive a que el servidor la mate (libracore ADR-044, varios workers).

Con `uvicorn --workers N`, un restore en caliente lo atiende UN worker; el intercambio de bases termina las conexiones de
la base viva, y la conexión de cada uno de los otros (`app.state.conn`, sin pool) queda muerta. Sin `ConexionRenovable`
cada request que la toca daba 500 hasta que alguien reiniciaba el contenedor. Estos tests matan la conexión con
`pg_terminate_backend` —lo mismo que hace el intercambio— y miran que el worker se recupere solo.
"""
import io
import sqlite3
import time

import psycopg
import pytest
from motor_de_test import TEST_DATABASE_URL

from app.conexion import ConexionRenovable
from app.db import connect
from app.services.modules import ModuleRepository


def _cruda() -> str:
    return TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _pid(conn) -> int:
    return conn._connection.info.backend_pid


def _matar(pid: int) -> None:
    """Lo que le hace el intercambio de un restore a las conexiones de la base viva, y espera a que se haya ido."""
    with psycopg.connect(_cruda(), autocommit=True) as otra:
        otra.execute("SELECT pg_terminate_backend(%s)", (pid,))
        limite = time.monotonic() + 10
        while otra.execute("SELECT 1 FROM pg_stat_activity WHERE pid = %s", (pid,)).fetchone():
            assert time.monotonic() < limite, "el servidor no terminó la conexión"
            time.sleep(0.05)


@pytest.fixture
def conn():
    c = connect(TEST_DATABASE_URL)
    c.execute("CREATE TABLE prueba_renovable (id SERIAL PRIMARY KEY, valor TEXT)")
    c.commit()
    assert isinstance(c, ConexionRenovable)
    yield c
    c.close()


def _filas(conn) -> int:
    return conn.execute("SELECT count(*) FROM prueba_renovable").fetchone()[0]


def test_el_worker_que_no_atendio_el_restore_se_recupera_solo(admin_client):
    """El caso real: la conexión de la app murió y el PRIMER request de después no se entera (ni da 500)."""
    app = admin_client.app
    vieja = _pid(app.state.conn)
    _matar(vieja)

    respuesta = admin_client.get("/catalog/categories")   # `CatalogService(request.app.state.conn)`

    assert respuesta.status_code == 200, respuesta.text
    assert _pid(app.state.conn) != vieja
    # `app.state.modules` guarda la MISMA conexión (se construyó una vez, al arrancar): también quedó viva.
    assert app.state.modules.is_enabled("facturacion") in (True, False)


def test_con_solo_lecturas_pendientes_el_statement_se_reintenta_sin_duplicar(conn):
    """Lo normal: la conexión casi nunca está `IDLE` (una lectura deja la transacción abierta) y de todos modos se recupera."""
    assert _filas(conn) == 0                      # un SELECT: la transacción queda abierta, sin escrituras
    vieja = _pid(conn)
    _matar(vieja)

    conn.execute("INSERT INTO prueba_renovable (valor) VALUES ('a')")
    conn.commit()

    assert _pid(conn) != vieja
    assert _filas(conn) == 1                      # el reintento no repite: la primera vez no llegó al servidor


def test_con_escrituras_pendientes_el_error_sube_y_nada_se_confirma_a_medias(conn):
    conn.execute("INSERT INTO prueba_renovable (valor) VALUES ('a')")   # escritura pendiente
    _matar(_pid(conn))

    with pytest.raises(Exception):  # noqa: B017 - no se reintenta: repetir sólo la 'b' confirmaría la transacción a medias
        conn.execute("INSERT INTO prueba_renovable (valor) VALUES ('b')")
    conn.rollback()                                                         # en una conexión rota es un no-op

    assert _filas(conn) == 0                      # el servidor deshizo la 'a' con la conexión
    conn.execute("INSERT INTO prueba_renovable (valor) VALUES ('c')")
    conn.commit()
    assert _filas(conn) == 1


def test_la_transaccion_que_cruzo_una_renovacion_con_escrituras_no_se_confirma(conn):
    """Con la conexión compartida por hilos, otro hilo puede renovarla mientras éste tiene la transacción a medias: lo
    que siga en esa transacción corre en la conexión nueva, y confirmarlo dejaría la 'b' sin la 'a'."""
    conn.execute("INSERT INTO prueba_renovable (valor) VALUES ('a')")
    _matar(_pid(conn))
    with pytest.raises(Exception):  # noqa: B017 - el hilo que se entera primero
        conn.execute("SELECT 1")
    conn.execute("SELECT 1")                      # el siguiente pedido renueva la conexión (sin rollback de por medio)

    conn.execute("INSERT INTO prueba_renovable (valor) VALUES ('b')")
    with pytest.raises(sqlite3.OperationalError):
        conn.commit()

    assert _filas(conn) == 0
    conn.execute("INSERT INTO prueba_renovable (valor) VALUES ('c')")   # y la siguiente transacción es normal
    conn.commit()
    assert _filas(conn) == 1


def test_un_commit_sobre_una_conexion_muerta_levanta_y_no_finge_haber_confirmado(conn):
    conn.execute("INSERT INTO prueba_renovable (valor) VALUES ('a')")
    _matar(_pid(conn))

    with pytest.raises(Exception):  # noqa: B017 - psycopg.OperationalError o su equivalente
        conn.commit()

    assert _filas(conn) == 0


def test_una_conexion_cerrada_a_mano_no_se_reabre_sola_pero_renovar_la_reabre_en_el_lugar(conn):
    modulos = ModuleRepository(conn)              # guarda la conexión, como `app.state.modules`
    conn.close()

    with pytest.raises(Exception):  # noqa: B017 - un pedido a mitad del restore no se cuela
        conn.execute("SELECT 1")

    conn.renovar()

    assert conn.execute("SELECT 1").fetchone()[0] == 1
    assert modulos.is_enabled("facturacion") in (True, False)   # el holder viejo ve la conexión nueva


def test_un_error_comun_no_renueva_la_conexion(conn):
    """Una violación de unicidad no es una conexión muerta: no hay reconexión ni reintento."""
    conn.execute("CREATE UNIQUE INDEX prueba_renovable_unico ON prueba_renovable (valor)")
    conn.execute("INSERT INTO prueba_renovable (valor) VALUES ('a')")
    conn.commit()
    pid = _pid(conn)

    with pytest.raises(Exception) as e:  # noqa: B017
        conn.execute("INSERT INTO prueba_renovable (valor) VALUES ('a')")
    conn.rollback()

    assert "unique" in str(e.value).lower() or "duplicate" in str(e.value).lower()
    assert _pid(conn) == pid
    assert _filas(conn) == 1


def test_el_restore_en_caliente_deja_viva_la_app(admin_client, monkeypatch):
    """El restore de verdad (`POST /api/config/restore`): `_reabrir_conexion` renueva la conexión en el lugar, y
    `app.state.modules` —que la guardó al arrancar— no queda con la vieja, ya cerrada (un `/config/arca` daba 500)."""
    for variable in ("VENTALIBRA_DATABASE_URL", "VENTALIBRA_LIBRACORE_DATABASE_URL", "VENTALIBRA_DB_PATH"):
        monkeypatch.setenv(variable, TEST_DATABASE_URL)       # las migraciones del restore buscan la base por variable
    bajada = admin_client.get("/api/config/backup-ahora")
    assert bajada.status_code == 200
    app = admin_client.app
    antes = app.state.conn

    restaurado = admin_client.post(
        "/api/config/restore", files={"backup_file": ("b.zip", io.BytesIO(bajada.content), "application/zip")},
    )

    assert restaurado.status_code == 200, restaurado.text
    assert app.state.conn is antes
    assert admin_client.get("/config/arca").status_code == 200   # gate `require_module("facturacion")` -> app.state.modules
    assert admin_client.get("/api/logs").status_code == 200       # app.state.auditoria
