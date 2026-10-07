"""Promociones («llevá N pagá M» y combos) montadas con los routers del motor (ADR-043).

El cálculo y el CRUD los prueba `libracommerce` (`tests/test_promociones.py`); acá, lo que es de este
producto: quién puede qué, que `POST /api/ventas` aplique las promociones con el ahorro dentro del
descuento, y que el cajero pueda pedir el precio de la lista predeterminada (lo que hace el POS).
"""
from ventas_helpers import abrir_turno, crear_item, registrar_venta


def _promo_2x1(client, item_id):
    r = client.post("/api/promociones", json={
        "nombre": "2x1", "tipo": "nxm", "paga": 1, "items": [{"producto_id": item_id, "cantidad": 2}],
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_las_reglas_las_carga_el_admin_y_el_cajero_no_las_toca(admin_client, cajero_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    promo = _promo_2x1(admin_client, item_id)
    assert [p["id"] for p in admin_client.get("/api/promociones").json()] == [promo["id"]]

    assert cajero_client.get("/api/promociones").status_code == 403
    assert cajero_client.post("/api/promociones", json={
        "nombre": "x", "tipo": "nxm", "paga": 1, "items": [{"producto_id": item_id, "cantidad": 2}],
    }).status_code == 403
    assert cajero_client.put(f"/api/promociones/{promo['id']}", json={
        "nombre": "x", "tipo": "nxm", "paga": 1, "items": [{"producto_id": item_id, "cantidad": 2}],
    }).status_code == 403
    assert cajero_client.delete(f"/api/promociones/{promo['id']}").status_code == 403


def test_el_cajero_calcula_que_promocion_aplica_a_su_carrito(admin_client, cajero_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    _promo_2x1(admin_client, item_id)
    r = cajero_client.post("/api/promociones/calcular", json={
        "items": [{"producto_id": item_id, "qty": 2, "precio": 100.0}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["ahorro"] == 100.0 and r.json()["aplicadas"][0]["nombre"] == "2x1"


def test_sin_sesion_no_se_calcula_ni_se_carga(admin_client):
    from conftest import https_client

    with https_client(admin_client.app) as anonimo:
        assert anonimo.post("/api/promociones/calcular", json={"items": []}).status_code == 401
        assert anonimo.get("/api/promociones").status_code == 401


def test_la_venta_aplica_la_promocion_y_el_ahorro_va_al_descuento(admin_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    promo = _promo_2x1(admin_client, item_id)
    abrir_turno(admin_client)

    # El POS cobra lo que el servidor va a registrar: subtotal 200 menos los 100 de la promoción.
    venta = registrar_venta(
        admin_client, item_id, precio="100.00", cantidad="2",
        pagos=[{"medio": "efectivo", "monto": 100.0}],
    )
    assert venta["subtotal"] == 200.0 and venta["descuento"] == 100.0 and venta["total"] == 100.0
    assert venta["promociones"] == [
        {"promocion_id": promo["id"], "nombre": "2x1", "veces": 1, "ahorro": 100.0}]
    detalle = admin_client.get(f"/api/ventas/{venta['id']}").json()
    assert detalle["promociones"] == venta["promociones"]


def test_una_venta_sin_promocion_aplicable_queda_igual(admin_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    _promo_2x1(admin_client, item_id)
    abrir_turno(admin_client)
    venta = registrar_venta(admin_client, item_id, precio="100.00", cantidad="1")
    assert venta["descuento"] == 0 and venta["total"] == 100.0 and venta["promociones"] == []


def test_el_cajero_lee_el_precio_de_la_lista_pero_no_los_quiebres(admin_client, cajero_client):
    """Lo que hace el POS: `GET /api/listas-precio/{id}/precio`. Vive en el router de quiebres, que es de
    admin; sin `require_staff_precio_admin_resto` el cajero recibía 403 y el POS caía al precio plano."""
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    lista = admin_client.post("/api/listas-precio", json={"nombre": "General"}).json()
    admin_client.post(f"/api/listas-precio/{lista['id']}/set-default")
    admin_client.put(f"/api/listas-precio/{lista['id']}/items/{item_id}/quiebres",
                     json={"quiebres": [{"min_quantity": 5, "amount": 80.0}]})
    admin_client.put(f"/api/listas-precio/{lista['id']}/items", json={"precios": {str(item_id): 100.0}})

    r = cajero_client.get(f"/api/listas-precio/{lista['id']}/precio",
                         params={"producto_id": item_id, "cantidad": 6})
    assert r.status_code == 200, r.text
    assert r.json() == {"precio": 80.0}
    # Los quiebres en sí, y todo lo que escribe, siguen siendo de admin (decisión del humano en #350).
    assert cajero_client.get(f"/api/listas-precio/{lista['id']}/items/{item_id}/quiebres").status_code == 403
    assert cajero_client.put(f"/api/listas-precio/{lista['id']}/items/{item_id}/quiebres",
                            json={"quiebres": []}).status_code == 403
    assert cajero_client.post(f"/api/listas-precio/{lista['id']}/set-default").status_code == 403


def test_el_cajero_no_lee_el_precio_con_otro_metodo(admin_client, cajero_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    lista = admin_client.post("/api/listas-precio", json={"nombre": "General"}).json()
    assert cajero_client.post(f"/api/listas-precio/{lista['id']}/precio",
                             params={"producto_id": item_id}).status_code in (403, 405)
