"""Cuanto hay de cada producto y DONDE.

`/reports/stock` ya existia, pero suma todo el parque por producto: dice que
hay 10 de algo, no en que sucursal estan. Con varios locales ese total no
alcanza para decidir nada.
"""


def _item(client, nombre, unidad="u"):
    client.post("/catalog/units", json={"code": unidad, "name": "Unidad"})
    return client.post("/catalog/items", json={"name": nombre, "unit_code": unidad}).json()["id"]


def _sucursal(client, nombre, tipo="store"):
    r = client.post("/locations", json={"name": nombre, "location_type": tipo})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _cargar(client, item_id, location_id, cantidad):
    r = client.post("/stock/adjustments", json={
        "item_id": item_id, "location_id": location_id,
        "quantity_delta": str(cantidad), "reason": "conteo",
    })
    assert r.status_code == 200, r.text


def _grilla(client, **params):
    r = client.get("/stock/por-deposito/grilla", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _fila(grilla, nombre):
    return next(i for i in grilla["items"] if i["nombre"] == nombre)


def test_el_stock_se_ve_abierto_por_deposito(admin_client):
    item = _item(admin_client, "Dulce de leche 1kg")
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 6)
    _cargar(admin_client, item, costanera, 4)

    g = _grilla(admin_client)
    fila = _fila(g, "Dulce de leche 1kg")
    assert float(fila["por_deposito"][str(centro)]) == 6.0
    assert float(fila["por_deposito"][str(costanera)]) == 4.0
    assert float(fila["total"]) == 10.0


def test_el_total_no_reemplaza_al_detalle(admin_client):
    """🔴 Lo que este endpoint agrega sobre `/reports/stock`.

    Dos repartos MUY distintos dan el mismo total. Si la pantalla mostrara
    sólo el total —que es lo que hay hoy— estos dos casos serían
    indistinguibles, y uno de los dos deja un local en cero.
    """
    todo_junto = _item(admin_client, "Todo en un local")
    repartido = _item(admin_client, "Repartido")
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")

    _cargar(admin_client, todo_junto, centro, 10)
    _cargar(admin_client, repartido, centro, 5)
    _cargar(admin_client, repartido, costanera, 5)

    g = _grilla(admin_client)
    a, b = _fila(g, "Todo en un local"), _fila(g, "Repartido")
    assert float(a["total"]) == float(b["total"]) == 10.0
    assert float(a["por_deposito"][str(costanera)]) == 0.0
    assert float(b["por_deposito"][str(costanera)]) == 5.0


def test_un_deposito_vacio_aparece_en_cero_y_no_se_omite(admin_client):
    """🔑 Un depósito que falta de la fila es indistinguible de uno que existe
    y está vacío, y la pregunta es justamente '¿de dónde saco esto?'."""
    item = _item(admin_client, "Yerba")
    centro = _sucursal(admin_client, "Centro")
    vacio = _sucursal(admin_client, "Depósito vacío", tipo="warehouse")
    _cargar(admin_client, item, centro, 3)

    fila = _fila(_grilla(admin_client), "Yerba")
    assert str(vacio) in fila["por_deposito"], "el depósito vacío no aparece"
    assert float(fila["por_deposito"][str(vacio)]) == 0.0


def test_un_producto_sin_ningun_movimiento_aparece_en_cero(admin_client):
    """Si no apareciera, quien carga el catálogo no ve lo que acaba de dar de
    alta y cree que se perdió."""
    _item(admin_client, "Recién creado")
    centro = _sucursal(admin_client, "Centro")

    fila = _fila(_grilla(admin_client), "Recién creado")
    assert float(fila["total"]) == 0.0
    assert float(fila["por_deposito"][str(centro)]) == 0.0


def test_la_transferencia_se_ve_reflejada_en_la_grilla(admin_client):
    """Las dos pantallas leen el MISMO ledger: lo que se mueve se ve acá."""
    item = _item(admin_client, "Dulce de leche 1kg")
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 10)

    admin_client.post("/stock/transferir", json={
        "item_id": item, "origen_id": centro, "destino_id": costanera, "cantidad": "4",
    })

    fila = _fila(_grilla(admin_client), "Dulce de leche 1kg")
    assert float(fila["por_deposito"][str(centro)]) == 6.0
    assert float(fila["por_deposito"][str(costanera)]) == 4.0
    assert float(fila["total"]) == 10.0, "una transferencia NO cambia el total"


def test_solo_con_stock_filtra_los_que_estan_en_cero(admin_client):
    con = _item(admin_client, "Con stock")
    _item(admin_client, "Sin stock")
    centro = _sucursal(admin_client, "Centro")
    _cargar(admin_client, con, centro, 1)

    todos = [i["nombre"] for i in _grilla(admin_client)["items"]]
    filtrados = [i["nombre"] for i in _grilla(admin_client, solo_con_stock=True)["items"]]
    assert "Sin stock" in todos
    assert "Sin stock" not in filtrados
    assert "Con stock" in filtrados


def test_un_cajero_puede_VER_el_stock(staff_client, admin_client):
    """Mirar cuánto hay es del mostrador: el router va con `staff_or_admin`."""
    item = _item(admin_client, "Yerba")
    centro = _sucursal(admin_client, "Centro")
    _cargar(admin_client, item, centro, 3)

    r = staff_client.get("/stock/por-deposito/grilla")
    assert r.status_code == 200, r.text
    assert float(_fila(r.json(), "Yerba")["por_deposito"][str(centro)]) == 3.0
