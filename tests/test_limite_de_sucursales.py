"""Las sucursales CONTRATADAS (ADR-073, decisión del dueño 2026-10-10): el dato vive en la instancia, el backoffice lo carga, y pasarse bloquea el alta
y la reactivación. Sin dato cargado no hay límite.

- el alta (`POST /api/sucursales`) y la reactivación (`PUT /api/sucursales/{id}` con `activa: true` sobre una dada de baja) cuentan las ACTIVAS: una más
  que las contratadas es 409 con un mensaje en castellano para el cliente;
- `GET /api/limites/sucursales` lo lee el admin o el backoffice; `PUT`, SÓLO el backoffice (token de servicio): el admin del cliente no se sube su tope.
"""
import pytest
from conftest import https_client
from libraauth.session_auth import SERVICE_TOKEN_ENV, SERVICE_TOKEN_HEADER
from motor_de_test import destino_dominio
from ventas_helpers import crear_sucursal

from app.main import create_app

TOKEN = "un-token-de-servicio-de-prueba"
SERVICIO = {SERVICE_TOKEN_HEADER: TOKEN}
RUTA = "/api/limites/sucursales"


def _contratar(client, n):
    from libracore import limites

    limites.fijar_sucursales_contratadas(n)


def _activas(client) -> int:
    return len(client.get("/api/sucursales").json())


def _dar_de_baja(client, sucursal):
    r = client.put(f"/api/sucursales/{sucursal['id']}", json={"nombre": sucursal["nombre"], "activa": False})
    assert r.status_code == 200, r.text


def _reactivar(client, sucursal):
    return client.put(f"/api/sucursales/{sucursal['id']}", json={"nombre": sucursal["nombre"], "activa": True})


@pytest.fixture
def sin_sesion(tmp_path):
    with https_client(create_app(destino_dominio(tmp_path / "ventalibra.db"))) as client:
        yield client


# ── El alta ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_con_una_contratada_la_segunda_sucursal_se_rechaza_con_el_mensaje(admin_client):
    _contratar(admin_client, 1)

    r = admin_client.post("/api/sucursales", json={"nombre": "Sucursal Este"})

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "Tu plan incluye 1 sucursal. Para sumar otra, comunicate con nosotros."
    assert _activas(admin_client) == 1  # no se creó nada


def test_con_dos_contratadas_la_segunda_entra_y_la_tercera_no(admin_client):
    _contratar(admin_client, 2)

    assert crear_sucursal(admin_client, "Sucursal Este")["nombre"] == "Sucursal Este"  # justo en el límite
    r = admin_client.post("/api/sucursales", json={"nombre": "Sucursal Oeste"})

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "Tu plan incluye 2 sucursales. Para sumar otra, comunicate con nosotros."
    assert _activas(admin_client) == 2


def test_sin_dato_cargado_no_hay_limite(admin_client):
    for nombre in ("A", "B", "C", "D"):
        crear_sucursal(admin_client, nombre)
    assert _activas(admin_client) == 5


def test_quitar_el_dato_levanta_el_limite(admin_client):
    from libracore import limites

    _contratar(admin_client, 1)
    assert admin_client.post("/api/sucursales", json={"nombre": "Este"}).status_code == 409
    limites.fijar_sucursales_contratadas(None)
    assert crear_sucursal(admin_client, "Este")["nombre"] == "Este"


def test_subir_lo_contratado_deja_sumar_la_que_estaba_trabada(admin_client):
    _contratar(admin_client, 1)
    assert admin_client.post("/api/sucursales", json={"nombre": "Este"}).status_code == 409
    _contratar(admin_client, 2)
    assert crear_sucursal(admin_client, "Este")["nombre"] == "Este"


def test_las_dadas_de_baja_no_cuentan_para_el_limite(admin_client):
    _contratar(admin_client, 2)
    este = crear_sucursal(admin_client, "Este")
    assert admin_client.post("/api/sucursales", json={"nombre": "Oeste"}).status_code == 409
    _dar_de_baja(admin_client, este)

    assert crear_sucursal(admin_client, "Oeste")["nombre"] == "Oeste"


def test_el_limite_se_lee_en_cada_pedido_no_al_armar_la_app(admin_client):
    """Cargar el número desde el backoffice con la instancia corriendo se ve en el pedido siguiente, sin reiniciar."""
    assert crear_sucursal(admin_client, "Este")["nombre"] == "Este"
    _contratar(admin_client, 2)
    assert admin_client.post("/api/sucursales", json={"nombre": "Oeste"}).status_code == 409


def test_el_modulo_apagado_sigue_ganando_con_su_403(admin_client):
    """Sin `multisucursal` (decisión administrativa) el rechazo es el del módulo, que viene primero, aunque haya límite."""
    admin_client.app.state.modules.set_enabled("multisucursal", False)
    _contratar(admin_client, 1)
    r = admin_client.post("/api/sucursales", json={"nombre": "Este"})
    assert r.status_code == 403, r.text
    assert "multisucursal" in r.json()["detail"]


# ── La reactivación ──────────────────────────────────────────────────────────────────────────────────────────────────


def test_reactivar_una_dada_de_baja_que_excede_lo_contratado_se_rechaza(admin_client):
    este = crear_sucursal(admin_client, "Este")
    _dar_de_baja(admin_client, este)
    _contratar(admin_client, 1)

    r = _reactivar(admin_client, este)

    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "Tu plan incluye 1 sucursal. Para sumar otra, comunicate con nosotros."
    assert [s["id"] for s in admin_client.get("/api/sucursales").json()].count(este["id"]) == 0  # sigue de baja


def test_reactivar_justo_en_el_limite_pasa(admin_client):
    este = crear_sucursal(admin_client, "Este")
    _dar_de_baja(admin_client, este)
    _contratar(admin_client, 2)

    r = _reactivar(admin_client, este)

    assert r.status_code == 200, r.text
    assert _activas(admin_client) == 2


def test_reactivar_sin_dato_cargado_no_tiene_limite(admin_client):
    este = crear_sucursal(admin_client, "Este")
    _dar_de_baja(admin_client, este)
    assert _reactivar(admin_client, este).status_code == 200


def test_editar_una_sucursal_ya_activa_no_cuenta_como_sumar_otra(admin_client):
    """Cambiar el nombre de una activa con el contrato al tope no es un alta: tiene que pasar."""
    este = crear_sucursal(admin_client, "Este")
    _contratar(admin_client, 1)  # el contrato quedó por debajo de las 2 activas

    r = admin_client.put(f"/api/sucursales/{este['id']}", json={"nombre": "Este renombrada", "activa": True})

    assert r.status_code == 200, r.text
    assert r.json()["nombre"] == "Este renombrada"


def test_con_el_contrato_por_debajo_de_las_activas_lo_que_existe_sigue_andando_y_no_se_suma(admin_client):
    crear_sucursal(admin_client, "Este")
    crear_sucursal(admin_client, "Oeste")
    _contratar(admin_client, 1)

    assert _activas(admin_client) == 3
    assert admin_client.post("/api/sucursales", json={"nombre": "Norte"}).status_code == 409


# ── El router de límites ─────────────────────────────────────────────────────────────────────────────────────────────


def test_get_dice_contratadas_y_activas(admin_client):
    assert admin_client.get(RUTA).json() == {"contratadas": None, "activas": 1}
    crear_sucursal(admin_client, "Este")
    _contratar(admin_client, 2)
    assert admin_client.get(RUTA).json() == {"contratadas": 2, "activas": 2}


def test_el_backoffice_carga_lo_contratado_con_el_token_y_la_instancia_lo_hace_cumplir(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    assert sin_sesion.get(RUTA, headers=SERVICIO).json() == {"contratadas": None, "activas": 1}

    r = sin_sesion.put(RUTA, json={"contratadas": 1}, headers=SERVICIO)

    assert r.status_code == 200, r.text
    assert r.json() == {"contratadas": 1, "activas": 1}
    from libracore import limites

    assert limites.sucursales_contratadas() == 1  # el dato quedó en la instancia
    with pytest.raises(limites.LimiteExcedido):
        limites.verificar_alta_de_sucursal(1)
    assert sin_sesion.put(RUTA, json={"contratadas": None}, headers=SERVICIO).json()["contratadas"] is None


def test_sin_sesion_ni_token_ni_lee_ni_escribe(sin_sesion):
    assert sin_sesion.get(RUTA).status_code == 401
    assert sin_sesion.put(RUTA, json={"contratadas": 5}).status_code == 401


def test_un_token_equivocado_o_sin_la_variable_no_entra(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    assert sin_sesion.put(RUTA, json={"contratadas": 5}, headers={SERVICE_TOKEN_HEADER: "otro"}).status_code == 401
    monkeypatch.delenv(SERVICE_TOKEN_ENV, raising=False)
    assert sin_sesion.put(RUTA, json={"contratadas": 5}, headers=SERVICIO).status_code == 401
    assert sin_sesion.get(RUTA, headers=SERVICIO).status_code == 401


def test_el_admin_de_la_instancia_lee_pero_no_puede_subirse_el_tope(admin_client):
    """🔴 El punto de la guarda separada: un tope que el propio admin del cliente cambia no topa nada."""
    _contratar(admin_client, 1)

    assert admin_client.get(RUTA).status_code == 200
    r = admin_client.put(RUTA, json={"contratadas": 50})

    assert r.status_code == 403, r.text
    assert admin_client.get(RUTA).json()["contratadas"] == 1


@pytest.mark.parametrize("malo", [0, -1, 1001, True, "muchas", 1.5])
def test_el_put_rechaza_lo_que_no_es_un_entero_valido(sin_sesion, monkeypatch, malo):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    assert sin_sesion.put(RUTA, json={"contratadas": malo}, headers=SERVICIO).status_code == 422
    assert sin_sesion.get(RUTA, headers=SERVICIO).json()["contratadas"] is None


def test_un_rol_que_no_es_admin_no_lee_el_contrato(admin_client):
    creado = admin_client.post("/users", json={"username": "u-cajero", "name": "Caja", "password": "clave-larga-1", "role": "cajero"})
    assert creado.status_code == 201, creado.text
    cajero = https_client(admin_client.app)
    assert cajero.post("/auth/login", json={"username": "u-cajero", "password": "clave-larga-1"}).status_code == 200
    assert cajero.get(RUTA).status_code == 403
    assert cajero.put(RUTA, json={"contratadas": 9}).status_code == 403


def test_el_token_no_abre_el_resto_de_las_sucursales(sin_sesion, monkeypatch):
    """El token de servicio llega a `/api/limites` y NADA más del dominio de sucursales: crear una sigue pidiendo sesión."""
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    assert sin_sesion.post("/api/sucursales", json={"nombre": "X"}, headers=SERVICIO).status_code == 401
