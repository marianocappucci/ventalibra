"""Un 409 no puede dejar la app sin poder escribir.

🔴 **El defecto que este archivo fija.** Este producto sostiene **una sola
conexion para toda la app** (`app.state.conn`, sin pool, abierta al arrancar y
nunca cerrada — es su diseño, heredado de SQLite). Contra PostgreSQL un error
**aborta la transaccion**, y toda consulta posterior sobre esa conexion muere
con *"current transaction is aborted, commands ignored until end of transaction
block"*.

Los endpoints que traducen un `IntegrityError` a un HTTP 409 —un codigo de
barras repetido, un SKU repetido, una segunda lista de precios por defecto— son
acciones **normales** de quien carga el catalogo. Sin un `rollback()` entre el
error y el 409, ese 409 se lleva puesto **todo lo que venga despues**, hasta que
alguien reinicie el contenedor.

`app/services/catalog.py::create_unit` ya lo hacia bien y lo dejo escrito: *"la
conexion es una sola para toda la app, asi que sin este rollback el 409 se lleva
puesto al que escriba despues"*. Lo que faltaba era que valiera para los otros
cuatro caminos, que delegan en el repositorio de LibraCommerce.

Los tests de abajo son de **integracion sobre HTTP**: piden el 409 por la ruta
real y despues intentan escribir otra cosa. Es la unica forma de ver el defecto,
porque cada pieza por separado se comporta bien.
"""
import pytest


def _unidad(client, code="u"):
    r = client.post("/catalog/units", json={"code": code, "name": "Unidad"})
    assert r.status_code in (200, 201, 409), r.text


def _item(client, name="Yerba"):
    _unidad(client)
    r = client.post("/catalog/items", json={
        "item_type": "product", "name": name, "unit_code": "u",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


@pytest.mark.parametrize("camino", ["codigo", "variante", "lista_default"])
def test_un_409_no_deja_la_app_sin_escribir(admin_client, camino):
    """Provoca el 409 por cada ruta que lo traduce, y despues escribe.

    🔑 **La segunda escritura es el test.** El 409 en si esta bien y siempre
    estuvo bien: es la respuesta correcta a un dato repetido. Lo que se mide es
    lo que pasa **despues**.
    """
    item_id = _item(admin_client, name=f"Item {camino}")

    if camino == "codigo":
        cuerpo = {"code_type": "barcode", "code": "7791234567890"}
        ruta = f"/catalog/items/{item_id}/codes"
    elif camino == "variante":
        cuerpo = {"sku": "SKU-REPETIDO", "name": "Talle M"}
        ruta = f"/catalog/items/{item_id}/variants"
    else:
        cuerpo = {"name": "Lista", "description": "", "is_default": True}
        ruta = "/pricing/lists"

    primera = admin_client.post(ruta, json=cuerpo)
    assert primera.status_code in (200, 201), primera.text

    repetida = admin_client.post(ruta, json=cuerpo)
    assert repetida.status_code in (409, 422), (
        f"esperaba el 409 del dato repetido, vino {repetida.status_code}"
    )

    # 🔴 Acá es donde se rompía: la conexión quedaba abortada y esto moría con
    # "current transaction is aborted" en vez de crear la unidad.
    despues = admin_client.post(
        "/catalog/units", json={"code": "kg", "name": "Kilogramo"}
    )
    assert despues.status_code in (200, 201), (
        f"despues del 409 la app no pudo escribir: {despues.status_code} "
        f"{despues.text[:200]}"
    )


def test_control_sin_409_la_segunda_escritura_anda(admin_client):
    """🔑 El control. Sin esto, una app que no pudiera escribir NUNCA haria
    fallar los tests de arriba por el motivo equivocado, y el rojo diria
    "despues del 409 no pudo escribir" sobre algo que no tiene que ver con el
    409.
    """
    _item(admin_client, name="Item control")
    r = admin_client.post("/catalog/units", json={"code": "lt", "name": "Litro"})
    assert r.status_code in (200, 201), r.text
