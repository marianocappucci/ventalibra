"""El ticket impreso y el detalle de una venta muestran las promociones que se le aplicaron.

El PDF lo arma LibraCore (ADR-012 de libracore, cubierto en su suite); acá, el puente: que
`GET /ventas/{id}/ticket` lea `sale_promotions` de ESA venta y se las pase al generador, que el
`descuento` no salga contado dos veces, y que una venta sin promociones imprima como siempre.
"""
from test_tickets import _texto_del_pdf
from ventas_helpers import abrir_turno, crear_item, registrar_venta


def _promo_2x1(client, item_id, nombre="2x1 alfajor"):
    r = client.post("/api/promociones", json={
        "nombre": nombre, "tipo": "nxm", "paga": 1, "items": [{"producto_id": item_id, "cantidad": 2}],
    })
    assert r.status_code == 200, r.text
    return r.json()


def _ticket(client, venta_id) -> str:
    r = client.get(f"/ventas/{venta_id}/ticket")
    assert r.status_code == 200, r.text
    return _texto_del_pdf(r.content)


def test_el_ticket_imprime_la_promocion_aplicada_y_no_repite_el_descuento(admin_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    _promo_2x1(admin_client, item_id)
    abrir_turno(admin_client)
    venta = registrar_venta(
        admin_client, item_id, precio="100.00", cantidad="2",
        pagos=[{"medio": "efectivo", "monto": 100.0}],
    )
    assert venta["descuento"] == 100.0

    texto = _ticket(admin_client, venta["id"])
    assert "Promo 2x1 alfajor" in texto
    # El ahorro es el ÚNICO descuento de la venta: sale en la fila de la promoción, no en otra «Descuento».
    assert "Descuento" not in texto


def test_el_ticket_muestra_cuantas_veces_se_aplico(admin_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    _promo_2x1(admin_client, item_id)
    abrir_turno(admin_client)
    venta = registrar_venta(
        admin_client, item_id, precio="100.00", cantidad="4",
        pagos=[{"medio": "efectivo", "monto": 200.0}],
    )
    assert "Promo 2x1 alfajor x2" in _ticket(admin_client, venta["id"])


def test_un_descuento_manual_junto_a_la_promocion_sigue_saliendo(admin_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    _promo_2x1(admin_client, item_id)
    abrir_turno(admin_client)
    r = admin_client.post("/api/ventas", json={
        "fecha": "2026-09-29", "descuento": 30.0,
        "items": [{"nombre": "Alfajor", "qty": 2, "precio": 100.0, "producto_id": item_id}],
        "pagos": [{"medio": "efectivo", "monto": 70.0}],
    })
    assert r.status_code == 200, r.text
    texto = _ticket(admin_client, r.json()["id"])
    assert "Promo 2x1 alfajor" in texto and "Descuento" in texto


def test_una_venta_sin_promociones_imprime_como_siempre(admin_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    abrir_turno(admin_client)
    venta = registrar_venta(admin_client, item_id, precio="100.00", cantidad="1")
    assert "Promo" not in _ticket(admin_client, venta["id"])


def test_el_ticket_de_una_venta_no_imprime_las_promociones_de_otra(admin_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    abrir_turno(admin_client)
    sin_promo = registrar_venta(admin_client, item_id, precio="100.00", cantidad="2")
    _promo_2x1(admin_client, item_id)
    con_promo = registrar_venta(
        admin_client, item_id, precio="100.00", cantidad="2",
        pagos=[{"medio": "efectivo", "monto": 100.0}],
    )
    assert "Promo" not in _ticket(admin_client, sin_promo["id"])
    assert "Promo 2x1 alfajor" in _ticket(admin_client, con_promo["id"])


def test_el_detalle_de_la_venta_trae_las_promociones_que_el_kit_muestra(admin_client):
    item_id = crear_item(admin_client, "Alfajor", "100.00")
    promo = _promo_2x1(admin_client, item_id)
    abrir_turno(admin_client)
    venta = registrar_venta(
        admin_client, item_id, precio="100.00", cantidad="2",
        pagos=[{"medio": "efectivo", "monto": 100.0}],
    )
    detalle = admin_client.get(f"/api/ventas/{venta['id']}").json()
    assert detalle["promociones"] == [
        {"promocion_id": promo["id"], "nombre": "2x1 alfajor", "veces": 1, "ahorro": 100.0}]
