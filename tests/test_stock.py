"""Stock por depósito y por variante, con el router de stock del motor (`/api/stock`, fase 6, ADR-033).

Antes esto era `/stock/adjustments` (un delta) y `GET /stock/{item}?location_id=`. Ahora el ajuste es `entrada`/`salida`/
`absoluto` sobre un depósito (`deposito_id`), y el saldo de un depósito y una variante vuelve en `stock_deposito`.
"""
from ventas_helpers import ajustar, crear_ubicacion, stock


def _make_item(client):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    created = client.post("/api/productos", json={"nombre": "Yerba 1kg", "unidad": "u"})
    return created.json()["id"]


def _make_location(client, name="Deposito"):
    return crear_ubicacion(client, name)["id"]


def test_current_stock_starts_at_zero(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    response = admin_client.get(f"/api/stock/{item_id}", params={"deposito_id": location_id})
    assert response.status_code == 200
    assert float(response.json()["stock_deposito"]) == 0.0
    assert float(response.json()["stock_actual"]) == 0.0


def test_manual_adjustment_updates_current_stock(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)

    adjust = ajustar(admin_client, item_id, location_id, "10", motivo="conteo inicial")
    assert adjust.status_code == 200, adjust.text

    assert float(stock(admin_client, item_id, location_id)) == 10.0


def test_negative_adjustment_decreases_stock(admin_client):
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    ajustar(admin_client, item_id, location_id, "10")
    ajustar(admin_client, item_id, location_id, "-3", motivo="rotura")
    assert float(stock(admin_client, item_id, location_id)) == 7.0


def test_fijar_en_compara_con_el_stock_de_ese_deposito(admin_client):
    """«Fijar en…» lleva el stock DE ESE DEPÓSITO al valor pedido, no el total: con dos depósitos, fijar uno en 4 no
    puede tocar al otro."""
    item_id = _make_item(admin_client)
    uno, otro = _make_location(admin_client, "Uno"), _make_location(admin_client, "Otro")
    ajustar(admin_client, item_id, uno, "10")
    ajustar(admin_client, item_id, otro, "3")

    r = admin_client.post(f"/api/stock/{item_id}/ajuste", json={"modo": "absoluto", "cantidad": 4, "deposito_id": uno})
    assert r.status_code == 200, r.text
    assert float(stock(admin_client, item_id, uno)) == 4.0
    assert float(stock(admin_client, item_id, otro)) == 3.0
    assert r.json()["stock_actual"] == 7.0  # el total sigue siendo la suma de los depósitos


def test_stock_is_tracked_independently_per_variant(admin_client):
    item_id = _make_item(admin_client)
    variant_m = admin_client.post(f"/api/productos/{item_id}/variantes", json={"sku": "V-M", "nombre": "M"}).json()
    variant_l = admin_client.post(f"/api/productos/{item_id}/variantes", json={"sku": "V-L", "nombre": "L"}).json()
    location_id = _make_location(admin_client)

    ajustar(admin_client, item_id, location_id, "10", variant_id=variant_m["id"])
    ajustar(admin_client, item_id, location_id, "5", variant_id=variant_l["id"])

    assert float(stock(admin_client, item_id, location_id, variant_m["id"])) == 10.0
    assert float(stock(admin_client, item_id, location_id, variant_l["id"])) == 5.0
    # Sin `variant_id` el saldo es el del ítem entero en ese depósito (todas las variantes): antes daba sólo lo
    # cargado sin variante. Es el contrato del motor, el mismo de `/reports/stock`.
    assert float(stock(admin_client, item_id, location_id)) == 15.0


def test_fijar_en_una_variante_no_toca_a_las_otras(admin_client):
    item_id = _make_item(admin_client)
    variant_m = admin_client.post(f"/api/productos/{item_id}/variantes", json={"sku": "V-M", "nombre": "M"}).json()
    variant_l = admin_client.post(f"/api/productos/{item_id}/variantes", json={"sku": "V-L", "nombre": "L"}).json()
    location_id = _make_location(admin_client)
    ajustar(admin_client, item_id, location_id, "10", variant_id=variant_m["id"])
    ajustar(admin_client, item_id, location_id, "5", variant_id=variant_l["id"])

    r = admin_client.post(f"/api/stock/{item_id}/ajuste", json={
        "modo": "absoluto", "cantidad": 2, "deposito_id": location_id, "variant_id": variant_m["id"]})
    assert r.status_code == 200, r.text
    assert float(stock(admin_client, item_id, location_id, variant_m["id"])) == 2.0
    assert float(stock(admin_client, item_id, location_id, variant_l["id"])) == 5.0
