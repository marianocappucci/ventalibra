"""Sin `VENTALIBRA_LIBRACORE_DATABASE_URL` el core es la base del dominio (ADR-094).

🔴 El defecto: `create_app()` resolvía el core con
`url_de_instancia("ventalibra", core=True, default="./data/ventalibra_libracore.db")` y `app/asgi.py` puenteaba la variable
histórica a un archivo SQLite de `DATA_DIR`. Con el producto sólo sobre PostgreSQL, `billing.configure` rechaza esa ruta: una
instancia sin la variable no arrancaba, y por eso el alta del motor (`_EXIGEN_LA_VARIABLE_DEL_CORE`, ADR-084 de libracore)
seguía escribiéndola. VentaLibra es de una sola base (`_UNA_SOLA_BASE`), así que sin variable el core ES la del dominio.

Se fija: (1) sin la variable arranca y el core es la URL del dominio, de punta a punta (login incluido); (2) con la variable a
la misma base (la forma vigente, la histórica y con `+psycopg`) anda igual; (3) con la variable a OTRA base se respeta, no se
pisa con la del dominio; (4) `app/asgi.py` ya no puentea el histórico a un archivo SQLite, y (5) una ruta SQLite sigue
rechazada (ese contrapeso está en `test_billing_url_no_es_ruta.py`).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import https_client
from motor_de_test import TEST_DATABASE_URL

from app import main as app_main
from app.main import create_app

RAIZ = Path(__file__).resolve().parent.parent
NOMBRES_DEL_CORE = ("VENTALIBRA_LIBRACORE_DATABASE_URL", "VENTALIBRA_LIBRACORE_DB_PATH")


class _Corte(Exception):
    """Para frenar `create_app()` justo después de resolver el core, sin necesitar una base real al otro lado."""


@pytest.fixture
def sin_variable_del_core(monkeypatch):
    for nombre in NOMBRES_DEL_CORE:
        monkeypatch.delenv(nombre, raising=False)
    return monkeypatch


@pytest.fixture
def core_pedido(monkeypatch):
    """Anota con qué URL `create_app()` configura el core. Deja pasar la llamada real."""
    pedidos = []
    original = app_main.billing.configure

    def espiar(db_path):
        pedidos.append(db_path)
        return original(db_path)

    monkeypatch.setattr(app_main.billing, "configure", espiar)
    return pedidos


def _arrancar_y_loguear(destino):
    app = create_app(destino)
    try:
        with https_client(app) as client:
            respuesta = client.post("/auth/login", json={"username": "admin", "password": "admin"})
            assert respuesta.status_code == 200, respuesta.text
            assert client.get("/api/clientes").status_code == 200   # el router del motor de core, por la base configurada
        return app
    finally:
        motor = getattr(app.state, "auth_engine", None)
        if motor is not None:
            motor.dispose()


def test_sin_la_variable_el_core_es_la_base_del_dominio(sin_variable_del_core, core_pedido):
    app = _arrancar_y_loguear(TEST_DATABASE_URL)

    assert core_pedido == [TEST_DATABASE_URL]
    assert app.state.auth_engine.url.database == TEST_DATABASE_URL.rsplit("/", 1)[1].split("?")[0]


@pytest.mark.parametrize("variable", NOMBRES_DEL_CORE)
@pytest.mark.parametrize("con_driver", [False, True], ids=["postgresql", "postgresql+psycopg"])
def test_con_la_variable_a_la_misma_base_se_respeta_y_anda(sin_variable_del_core, core_pedido, variable, con_driver):
    url = TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1) if con_driver else TEST_DATABASE_URL
    sin_variable_del_core.setenv(variable, url)

    _arrancar_y_loguear(TEST_DATABASE_URL)

    assert core_pedido == [url]


def test_con_la_variable_a_otra_base_se_respeta(sin_variable_del_core, monkeypatch):
    otra = "postgresql://ventalibra:clave@otro-servidor:5432/ventalibra_core_aparte"
    sin_variable_del_core.setenv("VENTALIBRA_LIBRACORE_DATABASE_URL", otra)
    pedidos = []

    def cortar(db_path):
        pedidos.append(db_path)
        raise _Corte

    monkeypatch.setattr(app_main.billing, "configure", cortar)

    with pytest.raises(_Corte):
        create_app(TEST_DATABASE_URL)

    assert pedidos == [otra]


def test_una_variable_vacia_cuenta_como_no_puesta(sin_variable_del_core, core_pedido):
    """Un `FOO=` sin interpolar en un compose no manda al core a la cadena vacía: cae al dominio."""
    sin_variable_del_core.setenv("VENTALIBRA_LIBRACORE_DATABASE_URL", "  ")

    _arrancar_y_loguear(TEST_DATABASE_URL)

    assert core_pedido == [TEST_DATABASE_URL]


def test_asgi_con_data_dir_no_puentea_el_core_a_un_archivo_sqlite(tmp_path):
    """El arranque real (`uvicorn app.asgi:app`) de una instancia provisionada: `DATA_DIR` y la URL del dominio, sin core."""
    entorno = {k: v for k, v in os.environ.items() if not k.startswith("VENTALIBRA_")}
    entorno.update({
        "PYTHONPATH": str(RAIZ / "tests"), "ENV": "development", "DATA_DIR": str(tmp_path / "data"),
        "VENTALIBRA_DATABASE_URL": TEST_DATABASE_URL,
    })
    codigo = (
        "import json, os\n"
        "import app.asgi as asgi\n"
        "print(json.dumps({'puente': os.environ.get('VENTALIBRA_LIBRACORE_DB_PATH'),"
        " 'core': asgi.app.state.auth_engine.url.database}))\n"
    )

    resultado = subprocess.run([sys.executable, "-c", codigo], env=entorno, cwd=RAIZ, capture_output=True, text=True, timeout=120)

    assert resultado.returncode == 0, resultado.stderr[-2000:]
    salida = json.loads(resultado.stdout.strip().splitlines()[-1])
    assert salida["puente"] is None
    assert salida["core"] == TEST_DATABASE_URL.rsplit("/", 1)[1].split("?")[0]
