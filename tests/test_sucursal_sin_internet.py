"""«Sucursal sin internet» en el central de VentaLibra (libraedge ADR-011, libra-ui ADR-080; ADR-090 de este producto).

La lógica es de LibraEdge y tiene sus tests allá; acá se prueba **la costura**: que el router está montado, que sólo
entra quien tiene `sucursales.admin` (el admin), que el aprovisionamiento es el de este producto (`app/offline.py`, la
guarda del adicional `offline` de libracore) y que el alta devuelve una carga que el instalador de VentaLibra acepta.
"""
import pytest
from libracore import adicionales
from libracore.db.core import get_connection
from libracore.db.modulos import set_addon
from libraedge.db.repository import NodeRepository
from libraedge.instalador import carga_desde_dict

RUTA = "/api/nodos-offline"


@pytest.fixture(autouse=True)
def _url_del_central(monkeypatch):
    monkeypatch.setenv("LIBRAEDGE_CENTRAL_URL", "https://demo.ventalibra.com.ar")


def _sucursal(cliente) -> str:
    return next(s["id"] for s in cliente.get(RUTA).json()["sucursales"] if s["activa"])


def test_el_encargado_no_entra(encargado_client):
    assert encargado_client.get(RUTA).status_code == 403
    assert encargado_client.post(RUTA, json={"sucursal_id": "1"}).status_code == 403


def test_el_admin_ve_el_estado_del_producto(admin_client):
    r = admin_client.get(RUTA)
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["producto"] == "ventalibra"
    assert datos["instalador_url"].endswith("/releases/latest/download/libraedge-nodo-ventalibra.exe")
    assert datos["central_url"] == "https://demo.ventalibra.com.ar"
    assert datos["contratado"] is False  # el adicional `offline` no viene en el plan único
    assert datos["nodos"] == []
    assert any(s["activa"] for s in datos["sucursales"])


def test_sin_el_adicional_no_se_da_de_alta(admin_client):
    r = admin_client.post(RUTA, json={"sucursal_id": _sucursal(admin_client)})
    assert r.status_code == 403
    assert r.json()["detail"]["codigo"] == "adicional_offline"
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM node_identity").fetchone()[0] == 0


def test_con_el_adicional_el_alta_devuelve_la_carga_y_la_baja_la_revoca(admin_client):
    set_addon("offline", True)
    adicionales.fijar_cantidad("offline", 1)
    assert admin_client.get(RUTA).json()["contratado"] is True

    r = admin_client.post(RUTA, json={"sucursal_id": _sucursal(admin_client)})
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["content-disposition"].startswith('attachment; filename="carga-nodo-')
    carga = carga_desde_dict(r.json(), "ventalibra")  # la que acepta el instalador de VentaLibra
    node_id = carga.entorno["LIBRAEDGE_NODE_ID"]
    secreto = carga.entorno["LIBRAEDGE_NODE_SECRET"]
    with get_connection() as conn:
        assert NodeRepository(conn).verify_node_secret(node_id, secreto)

    lista = admin_client.get(RUTA)
    assert secreto not in lista.text
    [nodo] = lista.json()["nodos"]
    assert nodo["node_id"] == node_id and nodo["estado"] == "nunca" and nodo["prefijo"].startswith("S")

    assert admin_client.delete(f"{RUTA}/{node_id}").status_code == 200
    with get_connection() as conn:
        assert not NodeRepository(conn).verify_node_secret(node_id, secreto)
