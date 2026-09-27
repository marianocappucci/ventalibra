"""Listas de precio con los routers del motor (`/api/listas-precio`, fase 7, ADR-034).

Hasta la fase 7 esto era `/pricing` (`app/routers/pricing.py`), que ninguna pantalla usaba. Ahora son
`build_listas_precio_router`, `build_quiebres_router` y `build_precios_vigentes_router` de `libracommerce`, los mismos de
Contalibra (más el de precios con vigencia y por sucursal, que armó VentaLibra). Configurar precios es de admin.

Lo que no pasó: la **lista predeterminada** (`is_default`, con su 409 si había dos y `resolve` sin lista). Nadie la usaba y el motor
no la tiene; el precio por defecto sigue siendo el del producto (`precio_venta`).
"""
from ventas_helpers import crear_item


def _lista(client, nombre="General", **extra):
    r = client.post("/api/listas-precio", json={"nombre": nombre, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _vigente(client, lista_id, item_id, monto, **extra):
    return client.post(
        f"/api/listas-precio/{lista_id}/items/{item_id}/precio-vigente", json={"monto": monto, **extra},
    )


def test_create_and_list_price_list(admin_client):
    lista = _lista(admin_client, "Mayorista", descripcion="por bulto")
    assert lista["nombre"] == "Mayorista" and lista["activa"]
    assert [l["nombre"] for l in admin_client.get("/api/listas-precio").json()] == ["Mayorista"]
    assert admin_client.post("/api/listas-precio", json={"nombre": "  "}).status_code == 422


def test_update_and_delete_price_list(admin_client):
    lista = _lista(admin_client, "General")
    r = admin_client.put(f"/api/listas-precio/{lista['id']}", json={"nombre": "General 2", "activa": False})
    assert r.status_code == 200 and r.json()["nombre"] == "General 2" and not r.json()["activa"]
    assert admin_client.put("/api/listas-precio/999", json={"nombre": "x"}).status_code == 404
    assert admin_client.delete(f"/api/listas-precio/{lista['id']}").json() == {"ok": True}
    assert admin_client.get("/api/listas-precio").json() == []


def test_set_and_list_item_prices(admin_client):
    item_id = crear_item(admin_client, "Fideos")
    lista = _lista(admin_client)

    created = _vigente(admin_client, lista["id"], item_id, 1300.0, desde="2026-01-01T00:00:00")
    assert created.status_code == 200, created.text

    vigencias = admin_client.get(f"/api/listas-precio/items/{item_id}/vigencias").json()
    assert len(vigencias) == 1
    assert float(vigencias[0]["monto"] if "monto" in vigencias[0] else vigencias[0]["amount"]) == 1300.0


def test_set_item_price_rejects_invalid_validity_window(admin_client):
    item_id = crear_item(admin_client, "Fideos")
    lista = _lista(admin_client)

    response = _vigente(admin_client, lista["id"], item_id, 1300.0,
                        desde="2026-01-01T00:00:00", hasta="2026-01-01T00:00:00")
    assert response.status_code == 422


def test_resolve_price_returns_none_without_configured_price(admin_client):
    item_id = crear_item(admin_client, "Fideos")
    lista = _lista(admin_client)

    response = admin_client.get(f"/api/listas-precio/{lista['id']}/precio", params={"producto_id": item_id})
    assert response.status_code == 200
    assert response.json()["precio"] is None


def test_resolve_price_uses_the_list(admin_client):
    item_id = crear_item(admin_client, "Fideos")
    lista = _lista(admin_client)
    _vigente(admin_client, lista["id"], item_id, 1300.0, desde="2026-01-01T00:00:00")

    response = admin_client.get(
        f"/api/listas-precio/{lista['id']}/precio", params={"producto_id": item_id, "en": "2026-06-01T00:00:00"},
    )
    assert response.status_code == 200, response.text
    assert float(response.json()["precio"]) == 1300.0


def test_los_precios_por_sucursal_y_por_cantidad(admin_client):
    """Lo que la lista de VentaLibra tiene y la de Contalibra no: un precio para una sucursal y quiebres por cantidad."""
    item_id = crear_item(admin_client, "Fideos")
    lista = _lista(admin_client)
    sucursal = next(d for d in admin_client.get("/api/depositos").json() if d["tipo"] == "store")
    assert _vigente(admin_client, lista["id"], item_id, 1000.0, desde="2026-01-01T00:00:00").status_code == 200
    assert _vigente(admin_client, lista["id"], item_id, 900.0, desde="2026-01-01T00:00:00",
                    sucursal_id=sucursal["id"]).status_code == 200
    en = "2026-06-01T00:00:00"
    de_la_sucursal = admin_client.get(f"/api/listas-precio/{lista['id']}/precio", params={
        "producto_id": item_id, "sucursal_id": sucursal["id"], "en": en}).json()["precio"]
    sin_sucursal = admin_client.get(f"/api/listas-precio/{lista['id']}/precio", params={
        "producto_id": item_id, "en": en}).json()["precio"]
    assert (float(de_la_sucursal), float(sin_sucursal)) == (900.0, 1000.0)

    r = admin_client.put(f"/api/listas-precio/{lista['id']}/items/{item_id}/quiebres",
                         json={"quiebres": [{"min_quantity": 10, "amount": 800.0}]})
    assert r.status_code == 200, r.text
    assert admin_client.get(f"/api/listas-precio/{lista['id']}/items/{item_id}/quiebres").json()


def test_las_listas_son_de_admin(admin_client, staff_client):
    lista = _lista(admin_client)
    assert staff_client.get("/api/listas-precio").status_code == 403
    assert staff_client.post("/api/listas-precio", json={"nombre": "Del cajero"}).status_code == 403
    assert staff_client.delete(f"/api/listas-precio/{lista['id']}").status_code == 403


def test_la_ruta_vieja_ya_no_existe(admin_client):
    assert admin_client.post("/pricing/lists", json={"name": "x"}).status_code in (404, 405)
