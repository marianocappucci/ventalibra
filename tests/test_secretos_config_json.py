"""Los secretos de `config.json` viven cifrados, no en el archivo (2026-09-17).

**Estos tests miran el `config.json` CRUDO y la tabla en la base**, no lo que
devuelve `config_manager.load()`. Es a proposito: `load()` devuelve el secreto
en claro por diseño -para que los consumidores no cambien- asi que un assert
sobre `load()` da verde igual con la implementacion vieja, la que escribia el
token en el archivo. Lo unico que distingue una de otra es que quedo en el
disco.

Y se mide a traves del enganche REAL del producto (`app.main.create_app`), no
armando un almacen a mano: lo que este archivo fija es que VentaLibra lo haya
enchufado, que es la mitad que LibraCore no puede garantizar.

A diferencia de contalibra (motor sqlite3 propio y `db_usuarios` como modulo
singleton), acá `create_app()` arma un engine y un `SecretosRepository` nuevos
por llamada -de ahi que se cuelguen de `app.state.secretos` /
`app.state.auth_engine` para que el test pueda llegar a ellos- y VentaLibra usa
la MISMA base de PostgreSQL para dominio y core (`TEST_DATABASE_URL`, ver
`motor_de_test.py`), asi que alcanza un solo `create_app(TEST_DATABASE_URL)`,
igual que `tests/test_arranque_exige_cadena_libraauth.py`.
"""
import json

import pytest
from libracore import config_manager as lc_config_manager
from motor_de_test import TEST_DATABASE_URL
from sqlalchemy import text

from app.main import create_app, migrar_secretos

TOKEN = "APP_USR-1234567890123456-091712-abcdef0123456789-3392230021"


def _crudo():
    with open(lc_config_manager.CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _escribir_crudo(datos):
    """Escribe el archivo como lo dejaba la version vieja, sin pasar por
    `save()` -que ya enruta al almacen y no dejaria el secreto en el
    archivo-."""
    with open(lc_config_manager.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(datos, f)


def _filas_de_secretos(app):
    with app.state.auth_engine.connect() as c:
        return dict(
            c.execute(text("select clave, valor_cifrado from secretos_instancia")).all()
        )


@pytest.fixture
def app():
    """App real contra el PostgreSQL de test. La fixture autouse `_dev_env`
    de `conftest.py` ya vacio el schema y corrio la cadena de libraauth
    (`secretos_instancia` sale de su revision `0002`) antes de que este
    fixture se ejecute."""
    return create_app(TEST_DATABASE_URL)


def test_el_producto_enchufo_el_almacen(app):
    """Sin esto, todo lo demas es la implementacion vieja: `config_manager`
    sin almacen escribe el secreto en el JSON, exactamente como antes."""
    assert lc_config_manager.almacen_de_secretos() is app.state.secretos


def test_guardar_el_token_no_lo_deja_en_el_archivo(app):
    cfg = lc_config_manager.load()
    cfg["mp_access_token"] = TOKEN
    cfg["empresa_nombre"] = "Compulibra SRL"
    lc_config_manager.save(cfg)

    crudo = _crudo()
    assert crudo["mp_access_token"] == ""
    # Control positivo del mismo barrido: lo que no es secreto si quedo escrito.
    assert crudo["empresa_nombre"] == "Compulibra SRL"
    # Y para los consumidores no cambio nada.
    assert lc_config_manager.load()["mp_access_token"] == TOKEN


def test_en_la_base_tampoco_esta_en_claro(app):
    cfg = lc_config_manager.load()
    cfg["mp_access_token"] = TOKEN
    lc_config_manager.save(cfg)

    filas = _filas_de_secretos(app)
    assert "mp_access_token" in filas
    assert TOKEN not in filas["mp_access_token"]
    assert filas["mp_access_token"].startswith("v1:")


def test_el_arranque_migra_lo_que_la_version_vieja_dejo_en_el_archivo():
    """🔑 El caso de las instancias vivas: el archivo tiene los secretos en
    claro, se despliega esta version, y el arranque (`create_app()`) los mueve
    solo. Por eso este test NO usa el fixture `app`: necesita escribir el
    archivo crudo ANTES de crear la app."""
    _escribir_crudo({
        "empresa_nombre": "Compulibra SRL",
        "mp_access_token": TOKEN,
        "mp_webhook_secret": "firma-del-webhook",
        "email_smtp_password": "la-contrasena",
    })
    assert _crudo()["mp_access_token"] == TOKEN  # el punto de partida

    app = create_app(TEST_DATABASE_URL)

    crudo = _crudo()
    for clave in lc_config_manager.CLAVES_SECRETAS:
        assert crudo[clave] == "", f"{clave} sigue en el archivo"
    assert crudo["empresa_nombre"] == "Compulibra SRL"
    assert lc_config_manager.load()["mp_access_token"] == TOKEN
    assert lc_config_manager.load()["mp_webhook_secret"] == "firma-del-webhook"
    filas = _filas_de_secretos(app)
    assert TOKEN not in filas["mp_access_token"]


def test_la_migracion_es_idempotente():
    _escribir_crudo({"mp_access_token": TOKEN})
    app = create_app(TEST_DATABASE_URL)
    antes = _filas_de_secretos(app)["mp_access_token"]

    informe = migrar_secretos()

    assert informe == {"migradas": [], "ya_estaban": [], "fallaron": {}}
    # No se reescribio: el blob es el mismo, con el mismo nonce.
    assert _filas_de_secretos(app)["mp_access_token"] == antes


def test_el_arranque_de_la_app_corre_la_migracion():
    """El enganche en `create_app()` y no solo la funcion suelta: sin la
    llamada a `migrar_secretos()` ahi adentro, la migracion existe y nadie la
    corre."""
    _escribir_crudo({"mp_access_token": TOKEN})

    create_app(TEST_DATABASE_URL)

    assert _crudo()["mp_access_token"] == ""
    assert lc_config_manager.load()["mp_access_token"] == TOKEN
