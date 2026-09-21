"""Transferencia de stock entre sucursales.

El caso que la motivo: Bioko, dos heladerias del mismo dueno que mueven
mercaderia de un local al otro. Antes de esto solo se podia hacer con dos
ajustes sueltos, que no quedan como transferencia y pierden mercaderia si el
segundo falla.
"""
from decimal import Decimal


def _item(client, nombre="Dulce de leche 1kg"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    return client.post("/catalog/items", json={"name": nombre, "unit_code": "u"}).json()["id"]


def _sucursal(client, nombre):
    r = client.post("/locations", json={"name": nombre, "location_type": "store"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _cargar(client, item_id, location_id, cantidad):
    r = client.post("/stock/adjustments", json={
        "item_id": item_id, "location_id": location_id,
        "quantity_delta": str(cantidad), "reason": "conteo inicial",
    })
    assert r.status_code == 200, r.text


def _stock(client, item_id, location_id) -> float:
    return float(client.get(f"/stock/{item_id}", params={"location_id": location_id}).json()["quantity"])


def test_la_mercaderia_sale_de_un_local_y_entra_en_el_otro(admin_client):
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 10)

    r = admin_client.post("/stock/transferir", json={
        "item_id": item, "origen_id": centro, "destino_id": costanera,
        "cantidad": "4", "nota": "reposicion del sabado",
    })
    assert r.status_code == 200, r.text

    assert _stock(admin_client, item, centro) == 6.0
    assert _stock(admin_client, item, costanera) == 4.0

    # La respuesta trae el stock de los dos lados para que la pantalla no
    # tenga que volver a preguntar.
    cuerpo = r.json()
    assert float(cuerpo["origen"]["stock"]) == 6.0
    assert float(cuerpo["destino"]["stock"]) == 4.0
    assert cuerpo["origen"]["nombre"] == "Centro"
    assert cuerpo["destino"]["nombre"] == "Costanera"


def test_no_se_puede_transferir_mas_de_lo_que_hay(admin_client):
    """🔴 El control que hace util a todo lo demas: sin esto el origen queda
    en negativo y el destino recibe mercaderia que no existe."""
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 3)

    r = admin_client.post("/stock/transferir", json={
        "item_id": item, "origen_id": centro, "destino_id": costanera, "cantidad": "5",
    })
    assert r.status_code == 422, r.text

    # Y NO se escribio ninguna de las dos patas: la transaccion es una sola.
    assert _stock(admin_client, item, centro) == 3.0
    assert _stock(admin_client, item, costanera) == 0.0


def test_origen_y_destino_iguales_no_mueven_nada(admin_client):
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    _cargar(admin_client, item, centro, 10)

    r = admin_client.post("/stock/transferir", json={
        "item_id": item, "origen_id": centro, "destino_id": centro, "cantidad": "2",
    })
    assert r.status_code == 422, r.text
    assert _stock(admin_client, item, centro) == 10.0


def test_cantidad_no_positiva_se_rechaza(admin_client):
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 10)

    for cantidad in ("0", "-3"):
        r = admin_client.post("/stock/transferir", json={
            "item_id": item, "origen_id": centro, "destino_id": costanera, "cantidad": cantidad,
        })
        assert r.status_code == 422, f"cantidad={cantidad}: {r.text}"
    assert _stock(admin_client, item, centro) == 10.0
    assert _stock(admin_client, item, costanera) == 0.0


def test_un_deposito_que_no_existe_da_404_y_no_422(admin_client):
    """404 y no 422: el pedido esta bien formado, lo que falta es la sucursal."""
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    _cargar(admin_client, item, centro, 10)

    r = admin_client.post("/stock/transferir", json={
        "item_id": item, "origen_id": centro, "destino_id": 9999, "cantidad": "1",
    })
    assert r.status_code == 404, r.text
    assert _stock(admin_client, item, centro) == 10.0


def test_el_historial_reconstruye_el_par_desde_el_ledger(admin_client):
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 10)
    admin_client.post("/stock/transferir", json={
        "item_id": item, "origen_id": centro, "destino_id": costanera,
        "cantidad": "4", "nota": "reposicion del sabado",
    })

    historial = admin_client.get("/stock/transferencias/historial").json()
    assert len(historial) == 1
    fila = historial[0]
    assert fila["origen"] == "Centro"
    assert fila["destino"] == "Costanera"
    assert Decimal(str(fila["cantidad"])) == Decimal("4")
    assert fila["nota"] == "reposicion del sabado"
    assert fila["item"] == "Dulce de leche 1kg"


def test_el_ajuste_manual_NO_aparece_como_transferencia(admin_client):
    """Control negativo: si el historial listara cualquier movimiento, este
    test pasaria igual y el de arriba no probaria nada."""
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    _cargar(admin_client, item, centro, 10)

    assert admin_client.get("/stock/transferencias/historial").json() == []


def test_el_historial_de_una_sucursal_trae_los_DOS_lados(admin_client):
    """Lo que salio y lo que entro: "¿que se movio de aca?" incluye lo que llego."""
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    deposito = _sucursal(admin_client, "Deposito")
    _cargar(admin_client, item, centro, 10)
    _cargar(admin_client, item, deposito, 10)

    admin_client.post("/stock/transferir", json={
        "item_id": item, "origen_id": centro, "destino_id": costanera, "cantidad": "1"})
    admin_client.post("/stock/transferir", json={
        "item_id": item, "origen_id": deposito, "destino_id": centro, "cantidad": "2"})
    admin_client.post("/stock/transferir", json={
        "item_id": item, "origen_id": deposito, "destino_id": costanera, "cantidad": "3"})

    de_centro = admin_client.get("/stock/transferencias/historial",
                                 params={"location_id": centro}).json()
    assert len(de_centro) == 2, [f["cantidad"] for f in de_centro]
    # La que no toca Centro ni de origen ni de destino queda afuera.
    assert all(centro in (f["origen_id"], f["destino_id"]) for f in de_centro)
    assert len(admin_client.get("/stock/transferencias/historial").json()) == 3


def test_un_cajero_SI_puede_transferir(admin_client, staff_client):
    """Decision del humano (2026-09-21): quien mueve la mercaderia entre
    locales es el encargado del mostrador, no el dueno.

    Se afirma el camino COMPLETO y no un "no da 403": que el cajero mande la
    transferencia y que el stock quede movido de verdad. Un test que solo
    mirara el codigo de estado pasaria igual si el endpoint aceptara el pedido
    y no escribiera nada.

    La preparacion va por `admin_client` —el alta de sucursales y de productos
    SI es de admin— y la transferencia por `staff_client`, que es lo que se
    esta probando. Las dos sesiones son de la misma instancia.
    """
    item = _item(admin_client)
    centro = _sucursal(admin_client, "Centro")
    costanera = _sucursal(admin_client, "Costanera")
    _cargar(admin_client, item, centro, 10)

    r = staff_client.post("/stock/transferir", json={
        "item_id": item, "origen_id": centro, "destino_id": costanera, "cantidad": "4",
    })
    assert r.status_code == 200, r.text
    assert _stock(admin_client, item, centro) == 6.0
    assert _stock(admin_client, item, costanera) == 4.0


def test_el_alta_de_sucursales_sigue_siendo_solo_de_admin(staff_client):
    """Control de que abrir la transferencia NO aflojo lo de al lado.

    Sin esto, un cambio que sacara `require_admin` de mas —del router de
    locations, por ejemplo— pasaria sin que ningun test lo note.
    """
    r = staff_client.post("/locations", json={"name": "Trucha", "location_type": "store"})
    assert r.status_code == 403, r.text
