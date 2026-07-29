"""Balanza de mostrador, de la configuracion al escaneo.

El parser en si esta cubierto en libracommerce (tests/test_scale.py). Aca
se prueba lo que agrega VentaLibra: que la configuracion persista, que el
scan resuelva el producto correcto con su cantidad, y que los dos modos de
balanza (peso e importe) terminen en un cobro distinto.
"""
from decimal import Decimal

import pytest


def _kilo(client):
    """La unidad kg. Se da de alta una sola vez por test: repetirla hoy
    levanta un IntegrityError crudo, no un 409."""
    if not any(u["code"] == "kg" for u in client.get("/catalog/units").json()):
        client.post(
            "/catalog/units",
            json={"code": "kg", "name": "Kilogramo", "allows_fraction": True, "decimal_scale": 3},
        )


def _producto_pesable(client, nombre="Queso cremoso", precio="8500"):
    """Un producto que se vende por kilo, con precio por kilo."""
    _kilo(client)
    creado = client.post(
        "/catalog/items",
        json={"name": nombre, "unit_code": "kg", "default_sale_price": precio},
    )
    assert creado.status_code == 200, creado.text
    return creado.json()["id"]


def _codigo_de_balanza(client, item_id, codigo="123"):
    respuesta = client.post(
        f"/catalog/items/{item_id}/codes", json={"code_type": "scale", "code": codigo},
    )
    assert respuesta.status_code == 200, respuesta.text


def _configurar(client, **cambios):
    config = {
        "prefix": "20", "code_digits": 5, "value_digits": 5,
        "value_kind": "weight", "divisor": 1000, "total_digits": 13,
    }
    config.update(cambios)
    respuesta = client.put("/settings/scale", json=config)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def test_sin_configurar_no_hay_balanza(admin_client):
    assert admin_client.get("/settings/scale").json() is None


def test_la_configuracion_persiste(admin_client):
    _configurar(admin_client, prefix="21", value_kind="amount", divisor=100)

    guardado = admin_client.get("/settings/scale").json()
    assert guardado["prefix"] == "21"
    assert guardado["value_kind"] == "amount"
    assert guardado["divisor"] == 100


def test_se_puede_apagar_la_balanza(admin_client):
    _configurar(admin_client)
    assert admin_client.delete("/settings/scale").status_code == 204
    assert admin_client.get("/settings/scale").json() is None


def test_una_configuracion_incoherente_se_rechaza(admin_client):
    # El codigo y el valor no entran en 13 digitos.
    respuesta = admin_client.put(
        "/settings/scale",
        json={"prefix": "20", "code_digits": 9, "value_digits": 9,
              "value_kind": "weight", "divisor": 1000, "total_digits": 13},
    )
    assert respuesta.status_code == 422


def test_escanear_una_etiqueta_devuelve_el_peso(admin_client):
    item_id = _producto_pesable(admin_client)
    _codigo_de_balanza(admin_client, item_id)
    _configurar(admin_client)

    # 20 | 00123 | 00750 | 4 -> producto 123, 750 gramos
    escaneo = admin_client.get("/catalog/items/scan", params={"code": "2000123007504"})
    assert escaneo.status_code == 200, escaneo.text
    cuerpo = escaneo.json()
    assert cuerpo["item"]["id"] == item_id
    assert Decimal(cuerpo["quantity"]) == Decimal("0.750")
    assert cuerpo["from_scale"] is True
    # Con peso, el precio no viene en la etiqueta: manda el del sistema.
    assert cuerpo["unit_price"] is None


def test_escanear_una_etiqueta_con_importe_calculado(admin_client):
    item_id = _producto_pesable(admin_client)
    _codigo_de_balanza(admin_client, item_id)
    _configurar(admin_client, value_kind="amount", divisor=100)

    # 20 | 00123 | 63750 | 4 -> producto 123, $637,50
    escaneo = admin_client.get("/catalog/items/scan", params={"code": "2000123637504"})
    cuerpo = escaneo.json()
    assert cuerpo["item"]["id"] == item_id
    # La etiqueta trae el importe y no dice cuanto peso: se cobra eso una
    # vez, no se inventa un peso dividiendo por el precio del sistema.
    assert Decimal(cuerpo["unit_price"]) == Decimal("637.50")
    assert Decimal(cuerpo["quantity"]) == 1


def test_con_la_balanza_apagada_la_etiqueta_es_un_codigo_cualquiera(admin_client):
    item_id = _producto_pesable(admin_client)
    _codigo_de_balanza(admin_client, item_id)

    # Sin configuracion, "2000123007504" no significa nada y no hay ningun
    # producto cargado con ese codigo de barras.
    assert admin_client.get(
        "/catalog/items/scan", params={"code": "2000123007504"}
    ).status_code == 404


def test_un_codigo_comun_sigue_funcionando_con_la_balanza_encendida(admin_client):
    item_id = _producto_pesable(admin_client, "Yerba")
    admin_client.post(
        f"/catalog/items/{item_id}/codes",
        json={"code_type": "barcode", "code": "7791234567890"},
    )
    _configurar(admin_client)

    cuerpo = admin_client.get(
        "/catalog/items/scan", params={"code": "7791234567890"}
    ).json()
    assert cuerpo["item"]["id"] == item_id
    assert cuerpo["from_scale"] is False
    assert Decimal(cuerpo["quantity"]) == 1


def test_una_etiqueta_de_un_producto_no_cargado_avisa_que_es_de_balanza(admin_client):
    _configurar(admin_client)

    respuesta = admin_client.get("/catalog/items/scan", params={"code": "2000999007504"})
    # 422 y no 404: la etiqueta se leyo bien, falta cargar el producto 999.
    assert respuesta.status_code == 422
    assert "999" in respuesta.json()["detail"]


def test_no_se_vende_por_peso_algo_que_va_por_unidad(admin_client):
    # Codigo de balanza cargado por error en un producto que se cuenta.
    admin_client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    creado = admin_client.post(
        "/catalog/items", json={"name": "Fosforos", "unit_code": "u", "default_sale_price": "500"},
    )
    _codigo_de_balanza(admin_client, creado.json()["id"])
    _configurar(admin_client)

    respuesta = admin_client.get("/catalog/items/scan", params={"code": "2000123007504"})
    assert respuesta.status_code == 422
    assert "fraccion" in respuesta.json()["detail"]


def test_el_codigo_de_balanza_no_choca_con_un_codigo_interno_igual(admin_client):
    queso = _producto_pesable(admin_client, "Queso")
    _codigo_de_balanza(admin_client, queso, "123")
    otro = _producto_pesable(admin_client, "Salame")
    admin_client.post(
        f"/catalog/items/{otro}/codes", json={"code_type": "internal", "code": "123"},
    )
    _configurar(admin_client)

    cuerpo = admin_client.get(
        "/catalog/items/scan", params={"code": "2000123007504"}
    ).json()
    assert cuerpo["item"]["id"] == queso


def test_el_cajero_no_configura_la_balanza(staff_client):
    assert staff_client.get("/settings/scale").status_code == 403


@pytest.mark.parametrize("codigo", ["2000123000000", "200012300750", "2000000007504"])
def test_etiquetas_mal_impresas_no_resuelven(admin_client, codigo):
    # Peso cero, largo equivocado y producto cero: ninguna es vendible, y
    # ninguna debe pasar por valida.
    item_id = _producto_pesable(admin_client)
    _codigo_de_balanza(admin_client, item_id)
    _configurar(admin_client)

    assert admin_client.get(
        "/catalog/items/scan", params={"code": codigo}
    ).status_code == 404


def test_una_venta_pesada_cobra_el_peso_por_el_precio_por_kilo(admin_client):
    item_id = _producto_pesable(admin_client, "Queso", precio="8500")
    _codigo_de_balanza(admin_client, item_id)
    _configurar(admin_client)

    escaneo = admin_client.get(
        "/catalog/items/scan", params={"code": "2000123007504"}
    ).json()

    venta = admin_client.post("/sales", json={}).json()
    agregado = admin_client.post(
        f"/sales/{venta['id']}/items",
        json={"item_id": item_id, "quantity": escaneo["quantity"]},
    )
    assert agregado.status_code == 200, agregado.text
    # 0,750 kg a $8500 el kilo = $6375
    assert Decimal(agregado.json()["total"]) == Decimal("6375.000")
