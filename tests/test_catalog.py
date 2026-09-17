from decimal import Decimal

from conftest import https_client


def _make_unit(client, code="u"):
    response = client.post("/catalog/units", json={"code": code, "name": "Unidad"})
    assert response.status_code == 200, response.text
    return response.json()


def _make_category(client, name="Almacen"):
    response = client.post("/catalog/categories", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


def test_create_and_list_category(admin_client):
    _make_category(admin_client, "Bebidas")
    response = admin_client.get("/catalog/categories")
    assert response.status_code == 200
    names = [c["name"] for c in response.json()]
    assert "Bebidas" in names


def test_create_and_list_unit(admin_client):
    _make_unit(admin_client, "kg")
    response = admin_client.get("/catalog/units")
    codes = [u["code"] for u in response.json()]
    assert "kg" in codes


def test_create_duplicate_unit_code_fails(admin_client):
    _make_unit(admin_client, "kg")

    response = admin_client.post("/catalog/units", json={"code": "kg", "name": "Kilogramo"})
    assert response.status_code == 409, response.text
    assert "kg" in response.json()["detail"]

    # La unidad original quedo intacta y la conexion sigue escribible: el
    # INSERT fallido no se lleva puesto lo que venga despues.
    codes = [u["code"] for u in admin_client.get("/catalog/units").json()]
    assert codes.count("kg") == 1
    assert _make_unit(admin_client, "u")["code"] == "u"


def test_create_item_with_unknown_unit_fails(admin_client):
    response = admin_client.post(
        "/catalog/items",
        json={"name": "Fideos", "unit_code": "no-existe"},
    )
    assert response.status_code == 422


def test_create_item_with_unknown_category_422(admin_client):
    # Antes de _validar_item esto reventaba la FK de Postgres y salia un 500
    # sin traducir -- ver ItemInvalido en services/catalog.py.
    _make_unit(admin_client, "u")
    response = admin_client.post(
        "/catalog/items",
        json={"name": "Fideos", "unit_code": "u", "category_id": 999},
    )
    assert response.status_code == 422, response.text


def test_create_item_empty_name_422(admin_client):
    _make_unit(admin_client, "u")
    response = admin_client.post(
        "/catalog/items", json={"name": "   ", "unit_code": "u"},
    )
    assert response.status_code == 422, response.text


def test_create_item_negative_price_422(admin_client):
    _make_unit(admin_client, "u")
    response = admin_client.post(
        "/catalog/items",
        json={"name": "Fideos", "unit_code": "u", "default_sale_price": "-1"},
    )
    assert response.status_code == 422, response.text


def test_create_item_negative_cost_422(admin_client):
    _make_unit(admin_client, "u")
    response = admin_client.post(
        "/catalog/items",
        json={"name": "Fideos", "unit_code": "u", "default_cost": "-1"},
    )
    assert response.status_code == 422, response.text


def test_create_and_get_item(admin_client):
    _make_unit(admin_client, "u")
    category = _make_category(admin_client, "Almacen")
    created = admin_client.post(
        "/catalog/items",
        json={
            "name": "Fideos 500g", "unit_code": "u", "category_id": category["id"],
            "default_sale_price": "1500.00", "default_cost": "900.00",
        },
    )
    assert created.status_code == 200, created.text
    item_id = created.json()["id"]

    fetched = admin_client.get(f"/catalog/items/{item_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Fideos 500g"
    assert float(fetched.json()["default_sale_price"]) == 1500.0


def test_get_unknown_item_404(admin_client):
    response = admin_client.get("/catalog/items/999")
    assert response.status_code == 404


def test_list_items_filters_by_search(admin_client):
    _make_unit(admin_client, "u")
    admin_client.post("/catalog/items", json={"name": "Arroz 1kg", "unit_code": "u"})
    admin_client.post("/catalog/items", json={"name": "Fideos 500g", "unit_code": "u"})

    response = admin_client.get("/catalog/items", params={"search": "Arroz"})
    assert response.status_code == 200
    names = [item["name"] for item in response.json()]
    assert names == ["Arroz 1kg"]


def _make_item(client, name="Fideos 500g"):
    _make_unit(client, "u")
    created = client.post("/catalog/items", json={"name": name, "unit_code": "u"})
    return created.json()["id"]


def test_add_and_list_codes(admin_client):
    item_id = _make_item(admin_client)

    added = admin_client.post(
        f"/catalog/items/{item_id}/codes",
        json={"code_type": "barcode", "code": "7791234567890", "is_primary": True},
    )
    assert added.status_code == 200, added.text

    listed = admin_client.get(f"/catalog/items/{item_id}/codes")
    assert listed.status_code == 200
    codes = listed.json()
    assert len(codes) == 1
    assert codes[0]["code"] == "7791234567890"
    assert codes[0]["is_primary"] is True


def test_scan_resolves_item_by_code(admin_client):
    item_id = _make_item(admin_client)
    admin_client.post(
        f"/catalog/items/{item_id}/codes", json={"code_type": "barcode", "code": "7791234567890"},
    )

    scanned = admin_client.get("/catalog/items/scan", params={"code": "7791234567890"})
    assert scanned.status_code == 200, scanned.text
    cuerpo = scanned.json()
    assert cuerpo["item"]["id"] == item_id
    # Un codigo comun no dice cuanto se lleva: siempre una unidad, y el
    # precio lo pone la lista de precios como siempre.
    assert Decimal(cuerpo["quantity"]) == 1
    assert cuerpo["unit_price"] is None
    assert cuerpo["from_scale"] is False


def test_scan_unknown_code_404(admin_client):
    response = admin_client.get("/catalog/items/scan", params={"code": "nope"})
    assert response.status_code == 404


def test_add_duplicate_code_within_same_type_fails(admin_client):
    item_a = _make_item(admin_client, "Item A")
    item_b = admin_client.post("/catalog/items", json={"name": "Item B", "unit_code": "u"}).json()["id"]
    admin_client.post(f"/catalog/items/{item_a}/codes", json={"code_type": "barcode", "code": "111"})

    response = admin_client.post(f"/catalog/items/{item_b}/codes", json={"code_type": "barcode", "code": "111"})
    assert response.status_code == 409


def test_add_and_list_variants(admin_client):
    item_id = _make_item(admin_client, "Remera")

    added = admin_client.post(
        f"/catalog/items/{item_id}/variants",
        json={"sku": "REM-M-AZUL", "name": "M / Azul", "attributes": {"talle": "M", "color": "azul"}},
    )
    assert added.status_code == 200, added.text
    assert added.json()["attributes"] == {"talle": "M", "color": "azul"}

    listed = admin_client.get(f"/catalog/items/{item_id}/variants")
    assert listed.status_code == 200
    variants = listed.json()
    assert len(variants) == 1
    assert variants[0]["sku"] == "REM-M-AZUL"


def test_add_duplicate_variant_sku_fails(admin_client):
    item_id = _make_item(admin_client, "Remera")
    admin_client.post(f"/catalog/items/{item_id}/variants", json={"sku": "REM-M", "name": "M"})

    response = admin_client.post(f"/catalog/items/{item_id}/variants", json={"sku": "REM-M", "name": "M otra vez"})
    assert response.status_code == 409


# ── PUT /catalog/items/{item_id} ─────────────────────────────────────────

def _update_payload(**overrides):
    """Body completo de ItemUpdate -- el PUT reemplaza el item entero (mismo
    criterio que ItemCreate), asi que cada test parte de esto y pisa lo que
    le interesa."""
    payload = {
        "name": "Fideos 500g", "unit_code": "u", "category_id": None,
        "description": "", "active": True, "sellable": True, "purchasable": True,
        "default_sale_price": "1500.00", "default_cost": "900.00",
    }
    payload.update(overrides)
    return payload


def _make_location(client, name="Deposito"):
    response = client.post("/locations", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_update_item_ok(admin_client):
    item_id = _make_item(admin_client)
    category = _make_category(admin_client, "Almacen")

    response = admin_client.put(
        f"/catalog/items/{item_id}",
        json=_update_payload(
            name="Fideos 500g (editado)", description="con salsa", category_id=category["id"],
            default_sale_price="1800.50", default_cost="950.25",
        ),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Fideos 500g (editado)"
    assert body["description"] == "con salsa"
    assert body["category_id"] == category["id"]
    assert Decimal(body["default_sale_price"]) == Decimal("1800.50")
    assert Decimal(body["default_cost"]) == Decimal("950.25")

    # El listado (que lee por GET, no lo que devolvio el PUT) tambien lo ve.
    fetched = admin_client.get(f"/catalog/items/{item_id}")
    assert fetched.json()["name"] == "Fideos 500g (editado)"


def test_update_item_deactivate(admin_client):
    item_id = _make_item(admin_client, "Descontinuado")

    response = admin_client.put(
        f"/catalog/items/{item_id}",
        json=_update_payload(name="Descontinuado", active=False),
    )
    assert response.status_code == 200, response.text
    assert response.json()["active"] is False

    # list_items filtra por active = 1 -- desactivar lo saca del listado.
    listado = admin_client.get("/catalog/items", params={"search": "Descontinuado"})
    assert listado.json() == []


def test_update_unknown_item_404(admin_client):
    _make_unit(admin_client, "u")
    response = admin_client.put("/catalog/items/999", json=_update_payload())
    assert response.status_code == 404


def test_update_item_unknown_unit_422(admin_client):
    item_id = _make_item(admin_client)
    response = admin_client.put(
        f"/catalog/items/{item_id}", json=_update_payload(unit_code="no-existe"),
    )
    assert response.status_code == 422


def test_update_item_unknown_category_422(admin_client):
    item_id = _make_item(admin_client)
    response = admin_client.put(
        f"/catalog/items/{item_id}", json=_update_payload(category_id=999),
    )
    assert response.status_code == 422


def test_update_item_empty_name_422(admin_client):
    item_id = _make_item(admin_client)
    response = admin_client.put(
        f"/catalog/items/{item_id}", json=_update_payload(name=""),
    )
    assert response.status_code == 422


def test_update_item_negative_price_422(admin_client):
    item_id = _make_item(admin_client)
    response = admin_client.put(
        f"/catalog/items/{item_id}", json=_update_payload(default_sale_price="-1"),
    )
    assert response.status_code == 422


def test_update_item_change_unit_without_movements_ok(admin_client):
    item_id = _make_item(admin_client)
    _make_unit(admin_client, "kg")

    response = admin_client.put(
        f"/catalog/items/{item_id}", json=_update_payload(unit_code="kg"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["unit_code"] == "kg"


def test_update_item_change_unit_with_stock_movement_fails_409(admin_client):
    item_id = _make_item(admin_client)
    _make_unit(admin_client, "kg")
    location_id = _make_location(admin_client)
    ajuste = admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "10", "reason": "carga inicial"},
    )
    assert ajuste.status_code == 200, ajuste.text

    response = admin_client.put(
        f"/catalog/items/{item_id}", json=_update_payload(unit_code="kg"),
    )
    assert response.status_code == 409, response.text
    assert "unidad" in response.json()["detail"]
    assert "movimientos" in response.json()["detail"]

    # El resto de los campos SI se edita, aunque la unidad quede bloqueada:
    # este PUT solo cambiaba la unidad, asi que el item queda intacto.
    assert admin_client.get(f"/catalog/items/{item_id}").json()["unit_code"] == "u"


def test_update_item_other_fields_edit_even_with_movements(admin_client):
    """El bloqueo es SOLO de la unidad -- el resto se edita siempre."""
    item_id = _make_item(admin_client)
    location_id = _make_location(admin_client)
    admin_client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "5", "reason": "carga inicial"},
    )

    response = admin_client.put(
        f"/catalog/items/{item_id}",
        json=_update_payload(name="Fideos 500g (con stock)", default_sale_price="2000"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Fideos 500g (con stock)"


def test_update_item_without_session_401(admin_client):
    # Mismo criterio que test_token_de_servicio.py::sin_sesion: una app ya
    # armada, un cliente nuevo que nunca hizo login. El router de catalogo se
    # monta con `dependencies=staff_or_admin` (app/main.py) -- cualquier
    # sesion valida (staff o admin) entra, asi que no hay un rol "de menos"
    # que probar aparte: lo que falta acá es la sesion misma.
    item_id = _make_item(admin_client)
    with https_client(admin_client.app) as sin_sesion:
        response = sin_sesion.put(f"/catalog/items/{item_id}", json=_update_payload())
    assert response.status_code == 401
