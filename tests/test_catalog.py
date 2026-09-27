"""Unidades y categorías del catálogo (`/catalog/units`, `/catalog/categories`).

Los productos son el router del motor desde la fase 7 (ADR-034): sus tests están en `test_productos.py`.
"""
from conftest import https_client
from ventas_helpers import producto_de


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


def test_create_category_empty_name_422(admin_client):
    response = admin_client.post("/catalog/categories", json={"name": "   "})
    assert response.status_code == 422, response.text


def test_create_duplicate_category_name_fails_422(admin_client):
    # El UNIQUE(parent_id, name) de la tabla no alcanza: las dos quedan con
    # parent_id NULL, y SQL no considera dos NULL iguales entre si -- el
    # chequeo es de _validar_category_name, no del INSERT. Ver su docstring.
    _make_category(admin_client, "Bebidas")
    response = admin_client.post("/catalog/categories", json={"name": "Bebidas"})
    assert response.status_code == 422, response.text
    assert "Bebidas" in response.json()["detail"]


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


# ── PUT /catalog/categories/{category_id} ────────────────────────────────

def test_update_category_ok(admin_client):
    category = _make_category(admin_client, "Almacen")

    response = admin_client.put(
        f"/catalog/categories/{category['id']}",
        json={"name": "Almacen seco", "active": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Almacen seco"
    assert body["active"] is True

    # El listado (por GET, no lo que devolvio el PUT) tambien lo ve.
    fetched = admin_client.get("/catalog/categories").json()
    assert any(c["id"] == category["id"] and c["name"] == "Almacen seco" for c in fetched)


def test_update_unknown_category_404(admin_client):
    response = admin_client.put("/catalog/categories/999", json={"name": "X", "active": True})
    assert response.status_code == 404


def test_update_category_empty_name_422(admin_client):
    category = _make_category(admin_client, "Almacen")
    response = admin_client.put(
        f"/catalog/categories/{category['id']}", json={"name": "   ", "active": True},
    )
    assert response.status_code == 422, response.text


def test_update_category_duplicate_name_422(admin_client):
    _make_category(admin_client, "Bebidas")
    otra = _make_category(admin_client, "Almacen")

    response = admin_client.put(
        f"/catalog/categories/{otra['id']}", json={"name": "Bebidas", "active": True},
    )
    assert response.status_code == 422, response.text


def test_update_category_same_name_ok(admin_client):
    # Guardar sin cambiar el nombre no debe chocar contra si misma -- el
    # chequeo de duplicado excluye category_id (exclude_id en
    # _validar_category_name).
    category = _make_category(admin_client, "Almacen")
    response = admin_client.put(
        f"/catalog/categories/{category['id']}", json={"name": "Almacen", "active": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["active"] is False


def test_deactivate_category_with_active_product_is_allowed(admin_client):
    # Desactivar esta permitido aunque un producto activo la use: el
    # producto conserva la categoria (no se toca catalog_items), solo deja
    # de ofrecerse para altas/ediciones nuevas -- eso es responsabilidad del
    # frontend (`libra-ui/comercio/Productos`) y del motor (`GET /api/productos/categorias`, sólo las activas), no de este
    # endpoint.
    _make_unit(admin_client, "u")
    category = _make_category(admin_client, "Almacen")
    item = admin_client.post(
        "/api/productos", json={"nombre": "Fideos", "unidad": "u", "categoria": "Almacen"},
    ).json()

    response = admin_client.put(
        f"/catalog/categories/{category['id']}", json={"name": "Almacen", "active": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["active"] is False

    # El producto sigue apuntando a la categoria, ahora inactiva.
    fetched_item = producto_de(admin_client, item["id"])
    assert fetched_item["categoria_id"] == category["id"]

    # GET /catalog/categories la sigue listando (con active=False) -- lo
    # necesita la pantalla de administracion para poder reactivarla, y la
    # edicion del producto para seguir mostrando su categoria actual.
    listado = admin_client.get("/catalog/categories").json()
    inactiva = next(c for c in listado if c["id"] == category["id"])
    assert inactiva["active"] is False


def test_reuse_name_of_a_deactivated_category(admin_client):
    # El chequeo de duplicado es contra categorias ACTIVAS -- desactivar
    # libera el nombre para una categoria nueva.
    vieja = _make_category(admin_client, "Bebidas")
    admin_client.put(f"/catalog/categories/{vieja['id']}", json={"name": "Bebidas", "active": False})

    response = admin_client.post("/catalog/categories", json={"name": "Bebidas"})
    assert response.status_code == 200, response.text


def test_update_category_without_session_401(admin_client):
    # Mismo criterio que test_update_item_without_session_401.
    category = _make_category(admin_client, "Almacen")
    with https_client(admin_client.app) as sin_sesion:
        response = sin_sesion.put(
            f"/catalog/categories/{category['id']}", json={"name": "Almacen", "active": True},
        )
    assert response.status_code == 401
