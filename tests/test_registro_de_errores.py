"""El registro de errores de la familia, montado en ESTE producto (ADR-045 de libracore).

El handler, el `ref`, la limpieza y el archivo los prueba el motor (`tests/test_errores.py`). Lo que se cuida acá es que
**esté cableado**: sin la línea `instalar_registro_de_errores(app, "ventalibra")` en `create_app()` un 500 sigue yendo
sólo al stdout de uvicorn y se pierde en cada recreate del contenedor, y el navegador no tiene a dónde mandar los suyos
(`POST /api/errores-cliente`). Si alguien la saca, los dos tests dan rojo.

🔑 El endpoint del navegador es público (un error del login también importa) y tampoco entra a la matriz de roles
(`test_roles_matriz.py`): no es una ruta del esquema de este producto sino del motor, igual que `/health`.
"""
import json

import pytest
from conftest import https_client
from fastapi.testclient import TestClient
from libracore import errores


@pytest.fixture
def carpeta_de_errores(tmp_path, monkeypatch):
    """El JSONL a un directorio propio del test y el cache de manejadores vacío (como en los tests del motor)."""
    monkeypatch.setenv("LIBRA_ERRORES_DIR", str(tmp_path / "errores"))
    monkeypatch.setenv("LIBRA_INSTANCIA", "ventalibra-test")
    monkeypatch.setenv("LIBRA_ENTORNO", "dev")
    monkeypatch.setattr(errores, "_manejadores", {})
    return tmp_path / "errores"


def _lineas(carpeta):
    archivo = carpeta / "errores.jsonl"
    if not archivo.exists():
        return []
    return [json.loads(x) for x in archivo.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_una_ruta_que_lanza_da_500_con_ref_y_deja_una_linea(admin_client, carpeta_de_errores):
    def explota():
        raise RuntimeError("falla de prueba")

    admin_client.app.add_api_route("/api/__falla_de_prueba", explota)
    # `raise_server_exceptions=False`: el TestClient por defecto relanza la excepción que el handler ya contestó.
    sin_relanzar = TestClient(admin_client.app, base_url="https://ventalibra.test", raise_server_exceptions=False)

    r = sin_relanzar.get("/api/__falla_de_prueba")

    assert r.status_code == 500
    cuerpo = r.json()
    assert cuerpo["detail"] == "Error interno"
    assert len(cuerpo["ref"]) == 8
    (linea,) = _lineas(carpeta_de_errores)
    assert linea["ref"] == cuerpo["ref"], "el ref que ve el usuario es el de la línea"
    assert linea["producto"] == "ventalibra"
    assert linea["instancia"] == "ventalibra-test" and linea["entorno"] == "dev"
    assert linea["tipo"] == "RuntimeError" and linea["status"] == 500 and linea["origen"] == "servidor"


def test_el_navegador_reporta_sin_sesion_y_queda_la_linea(admin_client, carpeta_de_errores):
    """`POST /api/errores-cliente` es público a propósito y lo monta la misma línea."""
    anonimo = https_client(admin_client.app)

    r = anonimo.post("/api/errores-cliente", json={
        "tipo": "error", "mensaje": "x is undefined", "stack": "TypeError: x\n    at f (/assets/index-abc.js:1:2)",
        "pagina": "/ventas/12/editar", "release": "dev",
    })

    assert r.status_code == 204
    (linea,) = _lineas(carpeta_de_errores)
    assert linea["origen"] == "cliente" and linea["producto"] == "ventalibra"
    assert linea["ruta"] == "/ventas/:id/editar"
