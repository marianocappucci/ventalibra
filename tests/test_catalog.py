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


def test_create_item_with_unknown_unit_fails(admin_client):
    response = admin_client.post(
        "/catalog/items",
        json={"name": "Fideos", "unit_code": "no-existe"},
    )
    assert response.status_code == 422


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
