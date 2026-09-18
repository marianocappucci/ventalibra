# --- Zona horaria de la suite ---------------------------------------------
# Argentina, UTC-3 fijo, sin horario de verano. Se fija ACA y no se hereda de
# la maquina: el CI y WSL corren en UTC, asi que un test que compare una
# fecha da distinto segun donde se corra, y a las 21:00 de Argentina el
# `date.today()` del proceso ya devuelve manana. Antes de cualquier import
# del producto, porque `tzset()` no alcanza a lo ya importado.
import os as _os
import time as _time

_os.environ["TZ"] = "America/Argentina/Buenos_Aires"
_time.tzset()

import pytest
from fastapi.testclient import TestClient
from motor_de_test import destino_dominio, destino_libracore, limpiar_entre_tests

from app.main import create_app


@pytest.fixture(autouse=True)
def _sin_almacen_de_secretos_colgado():
    """El almacen de secretos de `config_manager` no se filtra entre tests.

    `create_app()` llama a `config_manager.usar_almacen_de_secretos(...)`
    (libracore v1.108.0) con un repositorio atado a la base de ESE test, y es un
    global del proceso. Cuando la base se limpia, el almacen queda apuntando a
    conexiones que el servidor ya cerro, y el primer test posterior que llame a
    `config_manager.load()` sin levantar su propia app —el ticket lee de ahi el
    membrete— muere con `AdminShutdown`, lejisimos de su causa. Paso con
    `test_ticket_fecha_visible.py`, y en el CI de forma determinista.

    Antes y despues: antes por si un test anterior lo dejo puesto, despues para
    no ensuciar al que viene. Sin almacen, `config_manager` lee el JSON.
    """
    from libracore import config_manager

    config_manager.usar_almacen_de_secretos(None)
    yield
    config_manager.usar_almacen_de_secretos(None)


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch, tmp_path):
    # Una base vacia por TEST, no por app: varios tests arman dos apps y la
    # segunda le vaciaba el schema por debajo a la primera.
    limpiar_entre_tests()
    # SessionAuth's SECRET_KEY resolution and ensure_default_admin both
    # fail closed unless ENV=development -- see app/auth.py y
    # app/services/users.py::ensure_default_admin.
    monkeypatch.setenv("ENV", "development")
    # libracore.db es sqlite3 crudo (una conexion nueva por llamada, no un
    # engine con pool) -- ":memory:" le daria a cada llamada una base vacia
    # distinta. Un archivo temporal real por test, igual que medlibra/gestiolibra.
    monkeypatch.setenv(
        "VENTALIBRA_LIBRACORE_DB_PATH",
        destino_libracore(tmp_path / "ventalibra_libracore.db"),
    )
    # `libracore.config_manager` resuelve su ruta AL IMPORTARSE, desde
    # DATA_DIR o el cwd -- setear la variable acá ya llega tarde. Sin este
    # parche, cualquier test que guarde configuración (ticket, empresa)
    # escribe `config.json` en la raíz del repo y se lo lleva puesto entre
    # corridas. Detectado el 2026-07-28 al agregar la config del ticket.
    from libracore import config_manager
    monkeypatch.setattr(config_manager, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config_manager, "LOGO_DIR", str(tmp_path / "logos"))
    # Con la base en PostgreSQL la carpeta de backups sale de `DATA_DIR`
    # (`app.main._carpeta_de_backups`), y sin la variable cae en
    # `./data/backups`, adentro del checkout. Los dos tests de
    # `test_respaldo_postgres.py` que piden `/api/config/backup-ahora` dejaban
    # ahí un ZIP por corrida, **con el dump de la base adentro**. Estaba
    # arreglado sólo en `test_resguardo_externo_addon.py`, con su propio
    # fixture; va acá para que alcance a todos los tests.
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))


def https_client(app) -> TestClient:
    """SessionAuth's cookie es Secure -- httpx no la reenvia sobre http
    plano, y un host de un solo label ("testserver") tiene matching de
    dominio poco confiable en el cookie jar de httpx. Mismo fix que
    gestiolibra/medlibra: base_url https con host con punto."""
    return TestClient(app, base_url="https://ventalibra.test")


def _migrar_libracore(db_path: str) -> None:
    """Deja la base de LibraCore en `head`, como en producción.

    `create_app()` -> `app/services/billing.py::configure()` sólo corre
    `init_core_schema()` -- la baseline CONGELADA (ver su docstring: "por eso
    correrlas en cada arranque es un no-op sobre una base que ya las tiene").
    En una instancia real eso alcanza porque `libracore-migrar upgrade
    --prefijo <producto>` corre ANTES, en el `command` del compose y en
    `panel_admin.py actualizar` (ver DECISIONS.md/CLAUDE.md, "Git y Deploy").
    Sin ese paso acá, la suite nacía sin ninguna columna agregada por Alembic
    después de la baseline -- la que rompía D4 era `ventas_pagos.recibido`
    (migración `0010` de LibraCore), parcheada hasta ahora con un `ALTER
    TABLE` a mano en cada test que la necesitaba (`tests/ventas_helpers.py`/
    `tests/test_sales.py`).

    `upgrade()` es idempotente sobre lo que `init_core_schema()` ya creó
    (mismo criterio que usa `tests/test_migracion_0003.py::escenario`, que
    corre esta misma cadena sobre una base recién armada) -- no hay CREATE
    TABLE que choque con una tabla existente ni ALTER que se repita.

    🔴 **La cadena PROPIA de VentaLibra (`migrations/versions/`) NO se corre
    acá, a propósito.** `0001_baseline_ventalibra` llama exactamente a
    `init_commerce_schema()` + `init_schema_propio()` -- lo mismo que ya hace
    `create_app()` por su cuenta -- así que correrla de nuevo no agregaría
    schema, sólo estamparía `alembic_version_ventalibra`. `0002_created_at_
    hora_ar` corrige el DEFAULT de una columna que hoy no lee nadie
    (`sale_mp_orders.created_at`, ver su docstring) y `0003_capa_erp` es una
    migración de DATOS para una instancia que ya tiene ventas -- sobre una
    base vacía como la de cada test no tiene nada que migrar (su propio test,
    `test_migracion_0003.py`, la ejercita aparte, con el escenario que arma a
    mano). Correrla igual acá sumaría una dependencia entre el arranque de
    CADA test y el estado de una migración que además hace su propio
    `conn.commit()` fuera de la transacción de Alembic (ver el comentario en
    esa revisión) -- riesgo real por un schema que ya sale completo sin ella.
    Si algún día una revisión de VentaLibra agrega una columna que la suite
    necesita, se corre acá también, igual que se hizo con la de LibraCore.
    """
    from libracore.migrar import upgrade as _upgrade_libracore

    _upgrade_libracore(db_path)


@pytest.fixture
def admin_client(tmp_path):
    """App nueva contra un archivo SQLite temporal real (no :memory:, no
    mocks) + sesion logueada como el admin de bootstrap (admin/admin)."""
    db_path = destino_dominio(tmp_path / "ventalibra.db")
    app = create_app(db_path)
    # Misma base que `db_path`: `destino_libracore()` devuelve la MISMA URL
    # contra PostgreSQL (ver `motor_de_test.py`) -- las dos bases conviven en
    # un schema.
    _migrar_libracore(destino_libracore(tmp_path / "ventalibra_libracore.db"))
    with https_client(app) as client:
        response = client.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert response.status_code == 200, response.text
        try:
            yield client
        finally:
            # 🔴 Sin esto, cada test deja vivo el pool del engine de auth y la
            # corrida se come el `max_connections` del servidor. El sintoma
            # aparece lejos: mueren tests del medio con "too many clients" y el
            # que los causo paso en verde. Lo pago gestiolibra el 2026-08-31.
            motor = getattr(client.app.state, "auth_engine", None)
            if motor is not None:
                motor.dispose()


@pytest.fixture
def staff_client(admin_client: TestClient):
    """Segundo cliente logueado como staff, misma app/base que admin_client."""
    created = admin_client.post("/users", json={
        "username": "staff-1", "name": "Empleada", "password": "staff-pass", "role": "staff",
    })
    # 201 desde la adopción de `libraauth.usuarios.build_users_router`
    # (2026-09-13, ADR-018): la factory declara `status_code=201` en el alta,
    # a diferencia del router propio que reemplazó.
    assert created.status_code == 201, created.text
    with https_client(admin_client.app) as client:
        response = client.post("/auth/login", json={"username": "staff-1", "password": "staff-pass"})
        assert response.status_code == 200, response.text
        yield client



# ── Términos y Condiciones: aceptados para el resto de la suite ─────────────
#
# Desde libraauth v0.31.0 el motor corta con 403 **cualquier** llamada gateada
# por rol mientras la instancia no haya aceptado la versión vigente del
# contrato. Sin esta excepción, la suite entera se pone roja de golpe: cada
# test que loguea y pide datos recibe el 403 del gate en vez de lo que iba a
# medir, y el rojo no dice nada sobre el dominio.
#
# 🔴 **Esto NO apaga el gate donde importa.** Lo que la suite no puede es medir
# el dominio a través de un corte que no está probando; el corte tiene su propio
# archivo, `test_terminos_gate.py`, que se marca con `sin_aceptar_terminos` y
# queda afuera de esta excepción. Si alguien borrara el cableado de
# `app.state.terminos`, esa marca es lo único que se pondría rojo — el resto de
# la suite seguiría verde, porque no lo mira.


@pytest.fixture(autouse=True)
def _terminos_ya_aceptados(request):
    if request.node.get_closest_marker("sin_aceptar_terminos"):
        yield
        return

    from libraauth.terminos import TerminosRepository

    # 🔴 **`MonkeyPatch()` propio y no el fixture `monkeypatch`.** El fixture es
    # uno solo por test y lo comparten todas las fixtures que lo pidan, asi que
    # un `monkeypatch.undo()` en el cuerpo de un test —que existe, y es
    # legitimo— deshace TAMBIEN este parche y le prende el gate a la mitad del
    # test. El sintoma no se parece a la causa: la llamada siguiente devuelve
    # 403 y el test explota con un `KeyError` sobre la clave que esperaba en el
    # JSON. Lo encontro `test_despues_de_un_fallo_el_boton_puede_emitirlo` de
    # VentaLibra, que era el unico de las seis suites que llama `undo()`.
    mp = pytest.MonkeyPatch()
    mp.setattr(TerminosRepository, "esta_aceptada", lambda self: True)
    yield
    mp.undo()


# ── Captcha ALTCHA: dado por resuelto para el resto de la suite ─────────────
#
# Desde libraauth v0.40.0 el router corre con `captcha=True` (app/routers/
# auth.py): el login y el forgot-password exigen la solucion de un desafio.
# La suite postea al login en muchos lugares --los fixtures de sesion, los
# tests de auth, los de roles-- y resolver una prueba de trabajo en cada uno
# no mide nada de VentaLibra: el captcha (firma, vencimiento, anti-replay) lo
# prueba libraauth. Aca solo se CABLEA, y eso lo mide `test_captcha_login.py`,
# que se marca con `captcha_real` y queda afuera de esta excepcion.
#
# El router pide el captcha con la funcion de modulo
# `libraauth.session_auth._captcha_de(request)` en cada request, asi que se
# reemplaza esa funcion por un doble que acepta cualquier payload y emite
# desafios reales (baratos). La original queda en `_CAPTCHA_DE_REAL`, tomada
# al importar el conftest, antes de cualquier parche.
#
# `MonkeyPatch()` propio y no el fixture `monkeypatch`, por lo mismo que la
# excepcion de Terminos de arriba: `test_recibos.py` llama `monkeypatch.undo()`
# a mitad del test, y eso deshaceria tambien este parche.
from libraauth import session_auth as _session_auth  # noqa: E402
from libraauth.captcha import Captcha as _Captcha  # noqa: E402

_CAPTCHA_DE_REAL = _session_auth._captcha_de


class _CaptchaSiempreValido:
    """`verificar` acepta todo; `emitir` da un desafio de verdad, de costo
    minimo, para que `GET /auth/captcha` siga contestando con su forma."""

    def __init__(self):
        self._emisor = _Captcha("clave-de-prueba", costo=1, contador_min=1, contador_rango=5)

    def emitir(self) -> dict:
        return self._emisor.emitir()

    def verificar(self, payload: str) -> bool:
        return True


@pytest.fixture(autouse=True)
def _captcha_resuelto(request):
    if request.node.get_closest_marker("captcha_real"):
        yield
        return

    doble = _CaptchaSiempreValido()
    mp = pytest.MonkeyPatch()
    mp.setattr("libraauth.session_auth._captcha_de", lambda _request: doble)
    yield
    mp.undo()
