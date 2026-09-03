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


def https_client(app) -> TestClient:
    """SessionAuth's cookie es Secure -- httpx no la reenvia sobre http
    plano, y un host de un solo label ("testserver") tiene matching de
    dominio poco confiable en el cookie jar de httpx. Mismo fix que
    gestiolibra/medlibra: base_url https con host con punto."""
    return TestClient(app, base_url="https://ventalibra.test")


@pytest.fixture
def admin_client(tmp_path):
    """App nueva contra un archivo SQLite temporal real (no :memory:, no
    mocks) + sesion logueada como el admin de bootstrap (admin/admin)."""
    db_path = destino_dominio(tmp_path / "ventalibra.db")
    with https_client(create_app(db_path)) as client:
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
    assert created.status_code == 200, created.text
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
