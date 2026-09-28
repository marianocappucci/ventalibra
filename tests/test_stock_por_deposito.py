"""Cuánto hay de cada producto y DÓNDE (`GET /api/stock`, el router de stock del motor con `por_deposito`, fase 6).

`/reports/stock` ya existía, pero suma todo el parque por producto: dice que hay 10 de algo, no en qué sucursal están.
Con varios locales ese total no alcanza para decidir nada. Desde la fase 6 esto lo trae `GET /api/stock`: los
`depositos` (las columnas) y, en cada producto, `por_deposito` (`{deposito_id: cantidad}`, sólo los que tienen
movimientos: un depósito ausente es cero) y el total en `stock_actual`.
"""
from ventas_helpers import ajustar, crear_ubicacion


def _item(client, nombre, unidad="u"):
    client.post("/catalog/units", json={"code": unidad, "name": "Unidad"})
    return client.post("/api/productos", json={"nombre": nombre, "unidad": unidad}).json()["id"]


def _sucursal(client, nombre, tipo="store"):
    return crear_ubicacion(client, nombre, tipo)["id"]


def _cargar(client, item_id, location_id, cantidad):
    r = ajustar(client, item_id, location_id, cantidad, motivo="conteo")
    assert r.status_code == 200, r.text


def _stock(client):
    r = client.get("/api/stock")
    assert r.status_code == 200, r.text
    return r.json()


def _fila(datos, nombre):
    return next(p for p in datos["productos"] if p["nombre"] == nombre)


def _en(fila, deposito_id) -> float:
    """Un depósito ausente de `por_deposito` es cero: así lo lee la pantalla."""
    return float(fila["por_deposito"].get(str(deposito_id), 0))


def test_el_stock_se_ve_abierto_por_deposito(admin_client):
    item = _item(admin_client, "Dulce de leche 1kg")
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 6)
    _cargar(admin_client, item, costanera, 4)

    fila = _fila(_stock(admin_client), "Dulce de leche 1kg")
    assert _en(fila, centro) == 6.0
    assert _en(fila, costanera) == 4.0
    assert float(fila["stock_actual"]) == 10.0


def test_el_total_no_reemplaza_al_detalle(admin_client):
    """🔴 Lo que esto agrega sobre `/reports/stock`. Dos repartos MUY distintos dan el mismo total; si la pantalla
    mostrara sólo el total, estos dos casos serían indistinguibles, y uno de los dos deja un local en cero."""
    todo_junto = _item(admin_client, "Todo en un local")
    repartido = _item(admin_client, "Repartido")
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")

    _cargar(admin_client, todo_junto, centro, 10)
    _cargar(admin_client, repartido, centro, 5)
    _cargar(admin_client, repartido, costanera, 5)

    datos = _stock(admin_client)
    a, b = _fila(datos, "Todo en un local"), _fila(datos, "Repartido")
    assert float(a["stock_actual"]) == float(b["stock_actual"]) == 10.0
    assert _en(a, costanera) == 0.0
    assert _en(b, costanera) == 5.0


def test_un_deposito_vacio_es_una_columna_y_no_se_omite(admin_client):
    """🔑 Un depósito que falta es indistinguible de uno que existe y está vacío, y la pregunta es justamente '¿de
    dónde saco esto?': el depósito vacío está en `depositos` (es columna) aunque el producto no tenga nada en él."""
    item = _item(admin_client, "Yerba")
    centro = _sucursal(admin_client, "Centro")
    vacio = _sucursal(admin_client, "Depósito vacío", tipo="warehouse")
    _cargar(admin_client, item, centro, 3)

    datos = _stock(admin_client)
    assert vacio in [d["id"] for d in datos["depositos"]], "el depósito vacío no es columna"
    assert _en(_fila(datos, "Yerba"), vacio) == 0.0


def test_las_columnas_son_las_ubicaciones_activas(admin_client):
    baja = _sucursal(admin_client, "Depósito de baja", tipo="warehouse")
    admin_client.put(f"/api/depositos/{baja}", json={"nombre": "Depósito de baja", "activo": False})
    assert baja not in [d["id"] for d in _stock(admin_client)["depositos"]]


def test_un_producto_sin_ningun_movimiento_aparece_en_cero(admin_client):
    """Si no apareciera, quien carga el catálogo no ve lo que acaba de dar de alta y cree que se perdió."""
    _item(admin_client, "Recién creado")
    centro = _sucursal(admin_client, "Centro")

    fila = _fila(_stock(admin_client), "Recién creado")
    assert float(fila["stock_actual"]) == 0.0
    assert _en(fila, centro) == 0.0


def test_la_transferencia_se_ve_reflejada_en_el_stock(admin_client):
    """Las pantallas leen el MISMO ledger: lo que se mueve se ve acá."""
    item = _item(admin_client, "Dulce de leche 1kg")
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 10)

    admin_client.post("/api/depositos/transferir", json={
        "producto_id": item, "origen_id": centro, "destino_id": costanera, "cantidad": 4,
    })

    fila = _fila(_stock(admin_client), "Dulce de leche 1kg")
    assert _en(fila, centro) == 6.0
    assert _en(fila, costanera) == 4.0
    assert float(fila["stock_actual"]) == 10.0, "una transferencia NO cambia el total"


def test_un_cajero_puede_VER_el_stock(staff_client, admin_client):
    """Mirar cuánto hay es del mostrador: el router va con `staff_or_admin`."""
    item = _item(admin_client, "Yerba")
    centro = _sucursal(admin_client, "Centro")
    _cargar(admin_client, item, centro, 3)

    r = staff_client.get("/api/stock")
    assert r.status_code == 200, r.text
    assert _en(_fila(r.json(), "Yerba"), centro) == 3.0


def test_ajustar_el_stock_de_un_deposito_es_de_staff_y_admin_y_queda_en_el_historial(staff_client, admin_client):
    """Antes `POST /stock/adjustments` era de staff y admin (el router entero lo era). Se conserva: el ajuste no
    inventa mercadería que no se pueda ver en el historial, con quien lo hizo."""
    item = _item(admin_client, "Yerba")
    centro = _sucursal(admin_client, "Centro")

    r = ajustar(staff_client, item, centro, "5", motivo="conteo del cajero")
    assert r.status_code == 200, r.text
    assert r.json()["stock_deposito"] == 5.0
    movs = admin_client.get("/api/stock/movimientos", params={"producto_id": item}).json()
    assert [(m["cantidad"], m["referencia"], m["deposito_id"]) for m in movs] == [(5.0, "conteo del cajero", centro)]
    assert movs[0]["usuario_id"] is not None


def test_un_deposito_que_no_existe_no_se_ajusta(admin_client):
    item = _item(admin_client, "Yerba")
    r = ajustar(admin_client, item, 9999, "5")
    assert r.status_code == 422, r.text
    assert "9999" in r.json()["detail"]
