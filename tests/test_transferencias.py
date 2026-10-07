"""Transferencia de stock entre sucursales, con el router de depósitos del motor (`/api/depositos/transferir`, fase 6).

El caso que la motivó: Bioko, dos heladerías del mismo dueño que mueven mercadería de un local al otro. Antes de esto
sólo se podía hacer con dos ajustes sueltos, que no quedan como transferencia y pierden mercadería si el segundo falla.
"""
from ventas_helpers import ajustar, crear_ubicacion, stock


def _item(client, nombre="Dulce de leche 1kg"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    return client.post("/api/productos", json={"nombre": nombre, "unidad": "u"}).json()["id"]


def _sucursal(client, nombre):
    return crear_ubicacion(client, nombre, "store")["id"]


def _cargar(client, item_id, location_id, cantidad):
    r = ajustar(client, item_id, location_id, cantidad, motivo="conteo inicial")
    assert r.status_code == 200, r.text


def _stock(client, item_id, location_id) -> float:
    return float(stock(client, item_id, location_id))


def _transferir(client, item, origen, destino, cantidad, observaciones=""):
    return client.post("/api/depositos/transferir", json={
        "producto_id": item, "origen_id": origen, "destino_id": destino,
        "cantidad": float(cantidad), "observaciones": observaciones,
    })


def test_la_mercaderia_sale_de_un_local_y_entra_en_el_otro(admin_client):
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 10)

    r = _transferir(admin_client, item, centro, costanera, 4, "reposicion del sabado")
    assert r.status_code == 200, r.text

    assert _stock(admin_client, item, centro) == 6.0
    assert _stock(admin_client, item, costanera) == 4.0

    # La respuesta trae el stock de los dos lados para que la pantalla no tenga que volver a preguntar.
    cuerpo = r.json()
    assert cuerpo["origen"]["stock"] == 6.0
    assert cuerpo["destino"]["stock"] == 4.0
    assert cuerpo["origen"]["nombre"] == "Centro"
    assert cuerpo["destino"]["nombre"] == "Costanera"


def test_no_se_puede_transferir_mas_de_lo_que_hay(admin_client):
    """🔴 El control que hace útil a todo lo demás: sin esto el origen queda en negativo y el destino recibe
    mercadería que no existe."""
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 3)

    r = _transferir(admin_client, item, centro, costanera, 5)
    assert r.status_code == 422, r.text
    assert "insuficiente" in r.json()["detail"].lower()

    # Y NO se escribió ninguna de las dos patas: la transacción es una sola.
    assert _stock(admin_client, item, centro) == 3.0
    assert _stock(admin_client, item, costanera) == 0.0


def test_origen_y_destino_iguales_no_mueven_nada(admin_client):
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    _cargar(admin_client, item, centro, 10)

    r = _transferir(admin_client, item, centro, centro, 2)
    assert r.status_code == 422, r.text
    assert _stock(admin_client, item, centro) == 10.0


def test_cantidad_no_positiva_se_rechaza(admin_client):
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 10)

    for cantidad in (0, -3):
        r = _transferir(admin_client, item, centro, costanera, cantidad)
        assert r.status_code == 422, f"cantidad={cantidad}: {r.text}"
    assert _stock(admin_client, item, centro) == 10.0
    assert _stock(admin_client, item, costanera) == 0.0


def test_un_deposito_que_no_existe_o_esta_inactivo_da_422_con_su_nombre(admin_client):
    """422 y no 404 (cambió en la fase 6: es el contrato del motor, el de Contalibra): un depósito inexistente o
    dado de baja es un dato del pedido que nunca iba a dejar de fallar. Lo que importa es que no escriba nada y que el
    error diga cuál es el problema."""
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    _cargar(admin_client, item, centro, 10)

    r = _transferir(admin_client, item, centro, 9999, 1)
    assert r.status_code == 422, r.text
    assert "9999" in r.json()["detail"] and "no existe" in r.json()["detail"]
    assert _stock(admin_client, item, centro) == 10.0

    baja = crear_ubicacion(admin_client, "Depósito de baja", "warehouse")
    admin_client.put(f"/api/depositos/{baja['id']}", json={"nombre": "Depósito de baja", "activo": False})
    r = _transferir(admin_client, item, centro, baja["id"], 1)
    assert r.status_code == 422, r.text
    assert _stock(admin_client, item, centro) == 10.0


def test_el_historial_reconstruye_el_par_desde_el_ledger(admin_client):
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 10)
    _transferir(admin_client, item, centro, costanera, 4, "reposicion del sabado")

    historial = admin_client.get("/api/depositos/transferencias").json()
    assert len(historial) == 1
    fila = historial[0]
    assert fila["origen"] == "Centro"
    assert fila["destino"] == "Costanera"
    assert fila["cantidad"] == 4
    assert fila["observaciones"] == "reposicion del sabado"
    assert fila["producto"] == "Dulce de leche 1kg"


def test_el_ajuste_manual_NO_aparece_como_transferencia(admin_client):
    """Control negativo: si el historial listara cualquier movimiento, este test pasaría igual y el de arriba no
    probaría nada."""
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    _cargar(admin_client, item, centro, 10)

    assert admin_client.get("/api/depositos/transferencias").json() == []


def test_el_historial_de_una_sucursal_trae_los_DOS_lados(admin_client):
    """Lo que salió y lo que entró: "¿qué se movió de acá?" incluye lo que llegó."""
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    deposito = _sucursal(admin_client, "Deposito")
    _cargar(admin_client, item, centro, 10)
    _cargar(admin_client, item, deposito, 10)

    _transferir(admin_client, item, centro, costanera, 1)
    _transferir(admin_client, item, deposito, centro, 2)
    _transferir(admin_client, item, deposito, costanera, 3)

    de_centro = admin_client.get("/api/depositos/transferencias", params={"deposito_id": centro}).json()
    assert len(de_centro) == 2, [f["cantidad"] for f in de_centro]
    # La que no toca Centro ni de origen ni de destino queda afuera.
    assert all(centro in (f["origen_id"], f["destino_id"]) for f in de_centro)
    assert len(admin_client.get("/api/depositos/transferencias").json()) == 3


def test_un_encargado_SI_puede_transferir(admin_client, encargado_client):
    """Decisión del humano (2026-09-21): quien mueve la mercadería entre locales es el encargado del mostrador, no
    el dueño. Se afirma el camino COMPLETO (que el stock quede movido de verdad), no un «no da 403».

    La preparación va por `admin_client` —el alta de sucursales y de productos SÍ es de admin— y la transferencia por
    `encargado_client`, que es lo que se está probando.
    """
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 10)

    r = _transferir(encargado_client, item, centro, costanera, 4)
    assert r.status_code == 200, r.text
    assert _stock(admin_client, item, centro) == 6.0
    assert _stock(admin_client, item, costanera) == 4.0
    # Y lo que queda anotado lleva a quien la hizo.
    assert admin_client.get("/api/depositos/transferencias").json()[0]["usuario_id"] is not None


def test_el_alta_de_sucursales_sigue_siendo_solo_de_admin(encargado_client):
    """Control de que abrir la transferencia NO aflojó lo de al lado: con `autorizar_escritura` en el router, un cambio
    que lo sacara pasaría sin que ningún test lo note."""
    r = encargado_client.post("/api/depositos", json={"nombre": "Trucha", "tipo": "store"})
    assert r.status_code == 403, r.text
