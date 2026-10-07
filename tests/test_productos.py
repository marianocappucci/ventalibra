"""Productos con el router del motor (`/api/productos`, fase 7, ADR-034).

Hasta la fase 7 esto era `/catalog/items` (`app/routers/catalog.py`). Ahora es
`libracommerce.web.catalogo_router.build_productos_router`, el mismo de Contalibra y Restolibra, con las reglas de
VentaLibra como ganchos (`app/productos_ganchos.py`): la unidad tiene que existir y se bloquea con movimientos, la
categoría tiene que existir, precio y costo no negativos, el tipo no se cambia y un producto no se elimina.
"""
from conftest import https_client
from ventas_helpers import ajustar, crear_ubicacion, producto_de


def _make_unit(client, code="u", name="Unidad", **extra):
    response = client.post("/catalog/units", json={"code": code, "name": name, **extra})
    assert response.status_code in (200, 409), response.text


def _make_category(client, name="Almacen"):
    response = client.post("/catalog/categories", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()


def _make_item(client, name="Fideos 500g", **extra):
    _make_unit(client, "u")
    created = client.post("/api/productos", json={"nombre": name, "unidad": "u", **extra})
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _payload(**overrides):
    """Body completo: el `PUT` reemplaza el producto entero, así que cada test parte de esto y pisa lo que le
    interesa."""
    payload = {
        "nombre": "Fideos 500g", "codigo": "", "descripcion": "", "precio_venta": 1500.0, "precio_costo": 900.0,
        "unidad": "u", "categoria": "", "stock_minimo": 0, "tipo": "producto", "vendible": True, "activo": True,
    }
    payload.update(overrides)
    return payload


def _nombres(client, **params):
    r = client.get("/api/productos", params=params)
    assert r.status_code == 200, r.text
    return [p["nombre"] for p in r.json()]


# ── Alta ─────────────────────────────────────────────────────────────────


def test_create_item_with_unknown_unit_fails(admin_client):
    """La unidad la administra la instalación: una que no existe es 422, el motor no la crea al pasar."""
    response = admin_client.post("/api/productos", json={"nombre": "Fideos", "unidad": "no-existe"})
    assert response.status_code == 422, response.text
    assert "unidad desconocida" in response.json()["detail"]
    assert _nombres(admin_client) == []


def test_create_item_with_unknown_category_422(admin_client):
    _make_unit(admin_client)
    response = admin_client.post("/api/productos", json={"nombre": "Fideos", "unidad": "u", "categoria": "Inventada"})
    assert response.status_code == 422, response.text
    # El motor crearía la categoría al pasar; acá no: se administran en Configuración.
    assert all(c["name"] != "Inventada" for c in admin_client.get("/catalog/categories").json())


def test_create_item_in_an_inactive_category_422(admin_client):
    _make_unit(admin_client)
    cat = _make_category(admin_client, "Vieja")
    admin_client.put(f"/catalog/categories/{cat['id']}", json={"name": "Vieja", "active": False})
    response = admin_client.post("/api/productos", json={"nombre": "Fideos", "unidad": "u", "categoria": "Vieja"})
    assert response.status_code == 422, response.text


def test_create_item_empty_name_422(admin_client):
    _make_unit(admin_client)
    assert admin_client.post("/api/productos", json={"nombre": "   ", "unidad": "u"}).status_code == 422


def test_create_item_negative_price_and_cost_422(admin_client):
    _make_unit(admin_client)
    for campo in ("precio_venta", "precio_costo"):
        response = admin_client.post("/api/productos", json={"nombre": "Fideos", "unidad": "u", campo: -1})
        assert response.status_code == 422, f"{campo}: {response.text}"
    assert _nombres(admin_client) == []


def test_create_and_get_item(admin_client):
    _make_unit(admin_client)
    category = _make_category(admin_client, "Almacen")
    created = admin_client.post("/api/productos", json={
        "nombre": "Fideos 500g", "unidad": "u", "categoria": "Almacen", "precio_venta": 1500, "precio_costo": 900,
    })
    assert created.status_code == 200, created.text
    item = producto_de(admin_client, created.json()["id"])
    assert item["nombre"] == "Fideos 500g"
    assert item["precio_venta"] == 1500.0
    assert item["categoria"] == "Almacen" and item["categoria_id"] == category["id"]


def test_las_unidades_que_ofrece_el_alta_son_las_de_la_instalacion(admin_client):
    _make_unit(admin_client, "KG", "Kilogramo", allows_fraction=True, decimal_scale=3)
    _make_unit(admin_client, "UN", "Unidad")
    assert {"KG", "UN"} <= set(admin_client.get("/api/productos/unidades").json())
    assert "docena" not in admin_client.get("/api/productos/unidades").json()  # no la lista fija del motor


def test_guardar_un_producto_no_pisa_su_unidad(admin_client):
    """🔴 `_upsert_unit` reescribe la fila en cada guardado: sin conservarla, «Kilogramo» (escala 3) pasaba a `KG`
    (escala 0) y la balanza por peso dejaba de andar."""
    _make_unit(admin_client, "KG", "Kilogramo", allows_fraction=True, decimal_scale=3)
    item = admin_client.post("/api/productos", json={"nombre": "Queso", "unidad": "KG"}).json()
    admin_client.put(f"/api/productos/{item['id']}", json=_payload(nombre="Queso 2", unidad="KG"))
    kg = next(u for u in admin_client.get("/catalog/units").json() if u["code"] == "KG")
    assert kg == {"code": "KG", "name": "Kilogramo", "allows_fraction": True, "decimal_scale": 3}


# ── Búsqueda ─────────────────────────────────────────────────────────────


def test_list_items_filters_by_search(admin_client):
    _make_item(admin_client, "Arroz 1kg")
    _make_item(admin_client, "Fideos 500g")
    assert _nombres(admin_client, q="Arroz") == ["Arroz 1kg"]


def test_list_items_search_sin_distinguir_mayusculas(admin_client):
    # PostgreSQL es case-sensitive con LIKE (SQLite no): el lector de códigos andaba y sólo fallaba tipeando el nombre.
    _make_item(admin_client, "Cono Simple")
    for termino in ("CONO SIMPLE", "cono simple", "Cono"):
        assert _nombres(admin_client, q=termino) == ["Cono Simple"], f"buscando {termino!r}"


def test_list_items_search_varios_terminos_en_cualquier_orden(admin_client):
    _make_item(admin_client, "Cono Simple")
    _make_item(admin_client, "Cono Doble")
    # Orden invertido respecto del nombre, y espacios de sobra que no cuentan.
    assert _nombres(admin_client, q="  simple   cono  ") == ["Cono Simple"]


def test_list_items_search_termino_inexistente_no_encuentra(admin_client):
    _make_item(admin_client, "Cono Simple")
    assert _nombres(admin_client, q="chocolate") == []


def test_list_items_search_sin_distinguir_acentos(admin_client):
    # Decisión del humano: "cafe" encuentra "Café" y al revés, y la ñ ("nino" encuentra "Niño"). Sin
    # `CREATE EXTENSION unaccent`: es del motor (`libracommerce.erp.catalogo._sin_acentos_sql`).
    for nombre in ("Café", "Café con leche", "Niño Torta"):
        _make_item(admin_client, nombre)
    for termino in ("cafe", "café", "CAFÉ"):
        assert set(_nombres(admin_client, q=termino)) == {"Café", "Café con leche"}, termino
    assert _nombres(admin_client, q="nino") == ["Niño Torta"]


def test_el_pos_pide_solo_lo_activo(admin_client):
    _make_item(admin_client, "Vigente")
    baja = _make_item(admin_client, "De baja")
    admin_client.put(f"/api/productos/{baja}", json=_payload(nombre="De baja", activo=False))
    assert set(_nombres(admin_client)) == {"Vigente", "De baja"}  # la pantalla de productos ve todo
    assert _nombres(admin_client, solo_activos=True) == ["Vigente"]  # el POS no ve lo dado de baja


# ── Códigos, escaneo y variantes ─────────────────────────────────────────


def test_add_and_list_codes(admin_client):
    item_id = _make_item(admin_client)

    added = admin_client.post(
        f"/api/productos/{item_id}/codigos",
        json={"tipo": "barcode", "codigo": "7791234567890", "es_principal": True},
    )
    assert added.status_code == 200, added.text

    codigos = admin_client.get(f"/api/productos/{item_id}/codigos").json()
    assert [(c["codigo"], c["es_principal"]) for c in codigos] == [("7791234567890", True)]
    assert producto_de(admin_client, item_id)["codigo"] == "7791234567890"


def test_scan_resolves_item_by_code(admin_client):
    item_id = _make_item(admin_client)
    admin_client.post(f"/api/productos/{item_id}/codigos", json={"tipo": "barcode", "codigo": "7791234567890"})

    scanned = admin_client.get("/api/productos/escanear", params={"code": "7791234567890"})
    assert scanned.status_code == 200, scanned.text
    cuerpo = scanned.json()
    assert cuerpo["producto"]["id"] == item_id
    # Un código común no dice cuánto se lleva: siempre una unidad, y el precio lo pone la lista de precios.
    assert cuerpo["cantidad"] == 1
    assert cuerpo["precio_unitario"] is None
    assert cuerpo["de_balanza"] is False


def test_scan_unknown_code_404(admin_client):
    assert admin_client.get("/api/productos/escanear", params={"code": "nope"}).status_code == 404


def test_add_duplicate_code_within_same_type_fails(admin_client):
    item_a = _make_item(admin_client, "Item A")
    item_b = _make_item(admin_client, "Item B")
    admin_client.post(f"/api/productos/{item_a}/codigos", json={"tipo": "barcode", "codigo": "111"})

    response = admin_client.post(f"/api/productos/{item_b}/codigos", json={"tipo": "barcode", "codigo": "111"})
    assert response.status_code == 409


def test_add_and_list_variants(admin_client):
    item_id = _make_item(admin_client, "Remera")

    added = admin_client.post(
        f"/api/productos/{item_id}/variantes",
        json={"sku": "REM-M-AZUL", "nombre": "M / Azul", "atributos": {"talle": "M", "color": "azul"}},
    )
    assert added.status_code == 200, added.text
    assert added.json()["atributos"] == {"talle": "M", "color": "azul"}

    variantes = admin_client.get(f"/api/productos/{item_id}/variantes").json()
    assert [v["sku"] for v in variantes] == ["REM-M-AZUL"]


def test_add_duplicate_variant_sku_fails(admin_client):
    item_id = _make_item(admin_client, "Remera")
    admin_client.post(f"/api/productos/{item_id}/variantes", json={"sku": "REM-M", "nombre": "M"})

    response = admin_client.post(f"/api/productos/{item_id}/variantes", json={"sku": "REM-M", "nombre": "M otra vez"})
    assert response.status_code == 409


# ── Edición ──────────────────────────────────────────────────────────────


def test_update_item_ok(admin_client):
    item_id = _make_item(admin_client)
    category = _make_category(admin_client, "Almacen")

    response = admin_client.put(
        f"/api/productos/{item_id}",
        json=_payload(nombre="Fideos 500g (editado)", descripcion="con salsa", categoria="Almacen",
                      precio_venta=1800.5, precio_costo=950.25),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["nombre"] == "Fideos 500g (editado)"
    assert body["descripcion"] == "con salsa"
    assert body["categoria_id"] == category["id"]
    assert (body["precio_venta"], body["precio_costo"]) == (1800.5, 950.25)
    assert producto_de(admin_client, item_id)["nombre"] == "Fideos 500g (editado)"


def test_update_item_deactivate(admin_client):
    item_id = _make_item(admin_client, "Descontinuado")

    response = admin_client.put(f"/api/productos/{item_id}", json=_payload(nombre="Descontinuado", activo=False))
    assert response.status_code == 200, response.text
    assert not response.json()["activo"]
    assert _nombres(admin_client, q="Descontinuado", solo_activos=True) == []


def test_update_unknown_item_404(admin_client):
    _make_unit(admin_client)
    assert admin_client.put("/api/productos/999", json=_payload()).status_code == 404


def test_update_item_unknown_unit_422(admin_client):
    item_id = _make_item(admin_client)
    assert admin_client.put(f"/api/productos/{item_id}", json=_payload(unidad="no-existe")).status_code == 422


def test_update_item_unknown_category_422(admin_client):
    item_id = _make_item(admin_client)
    assert admin_client.put(f"/api/productos/{item_id}", json=_payload(categoria="Inventada")).status_code == 422


def test_update_item_empty_name_422(admin_client):
    item_id = _make_item(admin_client)
    assert admin_client.put(f"/api/productos/{item_id}", json=_payload(nombre="")).status_code == 422


def test_update_item_negative_price_422(admin_client):
    item_id = _make_item(admin_client)
    assert admin_client.put(f"/api/productos/{item_id}", json=_payload(precio_venta=-1)).status_code == 422


def test_el_tipo_no_se_cambia(admin_client):
    """Producto o servicio se elige al crear (antes `item_type` ni estaba en el payload de edición)."""
    item_id = _make_item(admin_client)
    response = admin_client.put(f"/api/productos/{item_id}", json=_payload(tipo="servicio"))
    assert response.status_code == 409, response.text
    assert producto_de(admin_client, item_id)["tipo"] == "producto"


def test_update_item_change_unit_without_movements_ok(admin_client):
    item_id = _make_item(admin_client)
    _make_unit(admin_client, "kg", "Kilogramo")

    response = admin_client.put(f"/api/productos/{item_id}", json=_payload(unidad="kg"))
    assert response.status_code == 200, response.text
    assert response.json()["unidad"] == "kg"


def test_update_item_change_unit_with_stock_movement_fails_409(admin_client):
    item_id = _make_item(admin_client)
    _make_unit(admin_client, "kg", "Kilogramo")
    location_id = crear_ubicacion(admin_client, "Deposito")["id"]
    assert ajustar(admin_client, item_id, location_id, "10", motivo="carga inicial").status_code == 200

    response = admin_client.put(f"/api/productos/{item_id}", json=_payload(unidad="kg"))
    assert response.status_code == 409, response.text
    assert "unidad" in response.json()["detail"] and "movimientos" in response.json()["detail"]
    assert producto_de(admin_client, item_id)["unidad"] == "u"


def test_update_item_other_fields_edit_even_with_movements(admin_client):
    """El bloqueo es SOLO de la unidad -- el resto se edita siempre."""
    item_id = _make_item(admin_client)
    location_id = crear_ubicacion(admin_client, "Deposito")["id"]
    ajustar(admin_client, item_id, location_id, "5", motivo="carga inicial")

    response = admin_client.put(
        f"/api/productos/{item_id}", json=_payload(nombre="Fideos 500g (con stock)", precio_venta=2000),
    )
    assert response.status_code == 200, response.text
    assert response.json()["nombre"] == "Fideos 500g (con stock)"


def test_editar_conserva_lo_que_el_formulario_no_maneja(admin_client):
    """`purchasable` y las claves de `metadata` que no manda el kit sobreviven a una edición (un `CatalogItem` nuevo los
    reseteaba a su default)."""
    item_id = _make_item(admin_client)
    conn = admin_client.app.state.conn
    conn.execute("UPDATE catalog_items SET purchasable = 0 WHERE id = ?", (item_id,))
    conn.commit()
    admin_client.put(f"/api/productos/{item_id}", json=_payload(nombre="Fideos 2"))
    assert conn.execute("SELECT purchasable FROM catalog_items WHERE id = ?", (item_id,)).fetchone()[0] in (0, False)


def test_un_producto_no_se_elimina_se_desactiva(admin_client):
    item_id = _make_item(admin_client)
    response = admin_client.delete(f"/api/productos/{item_id}")
    assert response.status_code == 409, response.text
    assert "desactivalo" in response.json()["detail"]
    assert producto_de(admin_client, item_id)["nombre"] == "Fideos 500g"


def test_las_categorias_se_administran_en_configuracion(admin_client):
    """El alta y la baja de categorías del motor están cerradas: las de este producto son jerárquicas y con baja
    lógica (`/catalog/categories`)."""
    assert admin_client.post("/api/productos/categorias", json={"nombre": "Suelta"}).status_code == 405
    cat = _make_category(admin_client, "Real")
    assert admin_client.delete(f"/api/productos/categorias/{cat['id']}").status_code == 405
    # Y la lectura sí, con sólo las activas.
    assert "Real" in [c["nombre"] for c in admin_client.get("/api/productos/categorias").json()]
    admin_client.put(f"/catalog/categories/{cat['id']}", json={"name": "Real", "active": False})
    assert "Real" not in [c["nombre"] for c in admin_client.get("/api/productos/categorias").json()]


def test_update_item_without_session_401(admin_client):
    item_id = _make_item(admin_client)
    with https_client(admin_client.app) as sin_sesion:
        response = sin_sesion.put(f"/api/productos/{item_id}", json=_payload())
    assert response.status_code == 401


def test_el_encargado_carga_y_edita_productos(admin_client, encargado_client):
    """Igual que antes con `/catalog/items`: la escritura del catálogo es de encargado y admin (`productos.escribir`)."""
    _make_unit(admin_client)
    r = encargado_client.post("/api/productos", json={"nombre": "Del cajero", "unidad": "u"})
    assert r.status_code == 200, r.text
    assert encargado_client.put(f"/api/productos/{r.json()['id']}", json=_payload(nombre="Del cajero 2")).status_code == 200
