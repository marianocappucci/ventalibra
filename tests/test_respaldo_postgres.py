"""El backup contra PostgreSQL trae la base -- no sale vacio.

🔴 El defecto: `Instancia` se armaba con `bases=[db_path, libracore_db_path]`,
y en PostgreSQL las dos son URLs, no rutas de archivo. `_copiar_base` hace
`if not origen.exists(): return` y una URL nunca "existe" como archivo, asi
que las salteaba LAS DOS en silencio -- el ZIP salia con los logos y sin
ninguna base, y `crear_backup()` no se quejaba. Recien se notaba al
restaurar (`verificar_backup` levanta `BackupInvalido`).

`admin_client` (`tests/conftest.py`) corre contra
`VENTALIBRA_TEST_DATABASE_URL` para las dos bases -- dominio y LibraCore
comparten la MISMA base en VentaLibra (`_UNA_SOLA_BASE`), asi que el caso
comun trae UNA sola base en el ZIP. El caso de una base de LibraCore
DISTINTA se prueba aparte, a nivel de `_instancia_de_respaldo` (unitario,
sin levantar una segunda base real) y de `libracore.respaldo` (con dos bases
reales en el mismo servidor, via `pg_dump`/`pg_restore`).
"""
import io
import zipfile

import psycopg
import pytest
from libracore.respaldo import Instancia, crear_backup, verificar_backup
from motor_de_test import TEST_DATABASE_URL

from app.main import _instancia_de_respaldo


def test_el_backup_trae_la_base_por_la_api(admin_client, tmp_path):
    r = admin_client.get("/api/config/backup-ahora")
    assert r.status_code == 200, r.text

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        bases = {n for n in z.namelist() if n.startswith("bases/")}

    assert bases == {"bases/ventalibra.dump"}, bases

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        contenido = z.read("bases/ventalibra.dump")
    assert contenido[:5] == b"PGDMP", contenido[:5]


def test_el_backup_de_la_api_no_escribe_en_el_checkout(admin_client, tmp_path):
    """El ZIP que arma `/api/config/backup-ahora` queda en `DATA_DIR`, que la
    suite apunta a `tmp_path` (`conftest.py::_dev_env`). Sin eso caía en
    `./data/backups` del repo: un dump de la base a un `git add` de subirse."""
    r = admin_client.get("/api/config/backup-ahora")
    assert r.status_code == 200, r.text

    zips = list((tmp_path / "data" / "backups").glob("*.zip"))
    assert zips, "el ZIP no quedó en el DATA_DIR temporal del test"


def test_el_zip_de_la_api_pasa_verificar_backup(admin_client, tmp_path):
    """No alcanza con que la API conteste 200: `verificar_backup` es el
    chequeo que de verdad importa (ver su docstring en `libracore.respaldo`)."""
    r = admin_client.get("/api/config/backup-ahora")
    zip_path = tmp_path / "descarga.zip"
    zip_path.write_bytes(r.content)
    instancia = _instancia_de_respaldo(
        TEST_DATABASE_URL, TEST_DATABASE_URL, str(tmp_path / "logos"),
    )

    resultado = verificar_backup(zip_path, instancia)

    assert set(resultado["bases"]) == {"ventalibra.dump"}
    assert resultado["bases"]["ventalibra.dump"] > 0


# ── `_instancia_de_respaldo`: cuándo suma la base de LibraCore aparte ──────

def test_misma_url_no_duplica_la_base_en_postgres_extra():
    inst = _instancia_de_respaldo(TEST_DATABASE_URL, TEST_DATABASE_URL, "/tmp/logos")

    assert inst.postgres_url == TEST_DATABASE_URL
    assert inst.postgres_extra == []
    assert inst.bases == []


def test_la_misma_url_con_el_driver_sqlalchemy_tampoco_duplica():
    """`postgresql://` y `postgresql+psycopg://` son la MISMA base -- una es
    la forma que entiende `pg_dump`/`libpq` y la otra la que arma SQLAlchemy.
    Sin normalizar, una instancia con las dos formas de la misma URL quedaría
    dumpeando la misma base dos veces bajo dos nombres."""
    plano = TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    con_driver = plano.replace("postgresql://", "postgresql+psycopg://", 1)

    inst = _instancia_de_respaldo(plano, con_driver, "/tmp/logos")

    assert inst.postgres_extra == []


def test_una_url_distinta_de_libracore_se_suma_aparte():
    otra = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/otra_base_distinta"

    inst = _instancia_de_respaldo(TEST_DATABASE_URL, otra, "/tmp/logos")

    assert inst.postgres_url == TEST_DATABASE_URL
    assert inst.postgres_extra == [otra]
    # Dos bases -> dos nombres distintos en el ZIP, ninguno pisa al otro.
    assert inst.nombres_en_zip == {"ventalibra.dump", "otra_base_distinta.dump"}


@pytest.mark.skipif(
    not TEST_DATABASE_URL.startswith("postgresql"),
    reason="necesita PostgreSQL real",
)
def test_con_dos_bases_reales_el_zip_trae_los_dos_dumps(tmp_path):
    """Caso de base core DISTINTA con datos reales: se crea una segunda base
    en el mismo servidor del `TEST_DATABASE_URL` y se corre `crear_backup` /
    `verificar_backup` de punta a punta, sin pasar por la app."""
    base_extra = "ventalibra_test_core_extra"
    admin_url = TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(admin_url, autocommit=True) as conexion:
        conexion.execute(f'DROP DATABASE IF EXISTS "{base_extra}"')
        conexion.execute(f'CREATE DATABASE "{base_extra}"')
    try:
        prefijo = admin_url.rsplit("/", 1)[0]
        url_extra = f"{prefijo}/{base_extra}"
        with psycopg.connect(url_extra, autocommit=True) as conexion:
            conexion.execute("CREATE TABLE marca_de_la_base_extra (id int)")

        instancia = Instancia(
            nombre="ventalibra", postgres_url=TEST_DATABASE_URL,
            postgres_extra=[url_extra],
        )
        destino = crear_backup(instancia, tmp_path / "backups")
        resultado = verificar_backup(destino, instancia)

        assert resultado["bases"].keys() == {"ventalibra.dump", f"{base_extra}.dump"}
        assert all(tam > 0 for tam in resultado["bases"].values())
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conexion:
            conexion.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{base_extra}' AND pid <> pg_backend_pid()"
            )
            conexion.execute(f'DROP DATABASE IF EXISTS "{base_extra}"')
