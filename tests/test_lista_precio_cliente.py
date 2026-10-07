"""La lista de precios asignada a un cliente (`/api/clientes/{id}/lista-precio`),
el router del motor extraído del add-on mayorista de Contalibra (ADR-010 de
libracommerce). A diferencia de Contalibra no hay add-on que lo gatee —listas
de precio es un módulo siempre libre desde la fase 7—, así que el permiso es
el de gerencia (encargado o admin): `clientes.lista_precio`. La lógica en sí
(upsert, FK, 404/422) la prueba `libracommerce/tests/test_web_cliente_lista.py`;
acá sólo el montaje y el gate en VentaLibra.
"""


def _cliente(admin_client, nombre="Distribuidora"):
    r = admin_client.post("/api/clientes", json={"name": nombre})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _lista(admin_client, nombre="Mayorista"):
    r = admin_client.post("/api/listas-precio", json={"nombre": nombre})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_un_encargado_puede_asignar_y_leer_la_lista(admin_client, encargado_client):
    cid = _cliente(admin_client)
    lid = _lista(admin_client)

    # El selector de la card carga las listas por este camino: con 403 quedaba sólo «precio base».
    assert [l["id"] for l in encargado_client.get("/api/listas-precio").json()] == [lid]
    assert encargado_client.get(f"/api/clientes/{cid}/lista-precio").json() == {"lista_id": None, "lista": None}
    r = encargado_client.put(f"/api/clientes/{cid}/lista-precio", json={"lista_id": lid})
    assert r.status_code == 200 and r.json()["lista_id"] == lid
    assert admin_client.get(f"/api/clientes/{cid}/lista-precio").json()["lista_id"] == lid


def test_un_cliente_inexistente_da_404(admin_client):
    assert admin_client.get("/api/clientes/999999/lista-precio").status_code == 404


def test_una_lista_inexistente_da_422(admin_client):
    cid = _cliente(admin_client)
    r = admin_client.put(f"/api/clientes/{cid}/lista-precio", json={"lista_id": 999999})
    assert r.status_code == 422
