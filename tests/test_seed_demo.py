"""El seed de la demo pública, corrido contra una base limpia.

**Por qué un test y no una corrida a mano contra una instancia.** El cron de
reset borra la base y vuelve a sembrar, así que lo que hay que garantizar es
que el seed funcione *desde cero* — que cada paso encuentre creado lo que
necesita. Probarlo contra una instancia ya sembrada no verifica eso: la mitad
de los pasos cae en la rama "ya estaba".

Lo que fijan estos tests, en orden de lo que se rompe sin que se note:

1. 🔴 **Que el seed corra entero sobre una base vacía.** El orden importa: los
   artículos necesitan la unidad y la categoría, el stock necesita el artículo
   y el depósito, las ventas necesitan todo lo anterior. Un paso fuera de orden
   falla sólo la primera vez, o sea justo en el reset.
2. 🔴 **Que las ventas queden confirmadas de verdad**, o sea que hayan
   descontado stock. Una venta creada y no confirmada se ve igual en el listado
   y no movió nada.
3. 🔴 **Que quede stock en cero y stock bajo.** La pantalla de faltantes existe
   para eso; con todo abastecido no muestra nada.
4. Que correrlo dos veces no duplique — el cron lo va a correr todos los días.
"""
import json

import pytest

from scripts.seed_demo import Api, sembrar, url_no_productiva


class _ApiDeTest(Api):
    """Habla con el `TestClient` con la misma interfaz que usa `sembrar()`, y
    **serializa igual que el `Api` real** (`default=str`): el seed manda
    `Decimal` y `datetime`, que el `json=` de httpx no sabe convertir. Con
    `json=` el doble fallaría donde el cliente de verdad anda, o sea probaría
    otra cosa."""

    def __init__(self, client):
        self.client = client

    def _pedir(self, metodo, ruta, cuerpo=None):
        datos = json.dumps(cuerpo, default=str) if cuerpo is not None else None
        respuesta = self.client.request(
            metodo, ruta, content=datos,
            headers={"Content-Type": "application/json"} if datos else None,
        )
        if respuesta.status_code >= 400:
            raise RuntimeError(f"{metodo} {ruta} -> {respuesta.status_code}: "
                               f"{respuesta.text[:300]}")
        return respuesta.json() if respuesta.content else None


@pytest.fixture
def api(admin_client):
    return _ApiDeTest(admin_client)


def _salon(api) -> int:
    """El id del depósito donde el seed carga el stock. El saldo es **por
    depósito**, así que preguntarlo sin decir cuál no tiene respuesta."""
    return next(d["id"] for d in api.get("/locations") if d["name"] == "Salón")


# ── 🔴 Desde cero ─────────────────────────────────────────────────────────

def test_el_seed_corre_entero_sobre_una_base_vacia(api, capsys):
    """El escenario del cron de reset."""
    sembrar(api)

    salida = capsys.readouterr().out
    assert "unidades     2 creados" in salida
    assert "artículos    11 creados" in salida
    assert "depósitos    2 creados" in salida


def test_deja_el_catalogo_completo(api):
    sembrar(api)

    assert len(api.get("/catalog/units")) == 2
    assert len(api.get("/catalog/categories")) == 4
    assert len(api.get("/catalog/items")) == 11
    assert len(api.get("/customers")) == 4
    assert len(api.get("/suppliers")) == 2


def test_hay_una_unidad_con_fraccion(api):
    """Es lo que hace posible vender 0,350 kg de queso. Sin al menos una así,
    la balanza y los decimales del ticket no se ejercitan."""
    sembrar(api)

    unidades = api.get("/catalog/units")
    assert any(u["allows_fraction"] for u in unidades)
    assert any(not u["allows_fraction"] for u in unidades)


# ── 🔴 Las ventas, confirmadas de verdad ──────────────────────────────────

def _ventas(api):
    lista = api.get("/sales") or []
    if isinstance(lista, dict):
        lista = next((v for v in lista.values() if isinstance(v, list)), [])
    return lista


def test_deja_ventas_cargadas(api):
    sembrar(api)

    assert len(_ventas(api)) >= 4


def test_las_ventas_descontaron_stock(api):
    """🔴 Confirmar es lo que descuenta stock y mueve la caja. Una venta creada
    y no confirmada aparece igual en el listado, así que contar ventas no
    distingue — hay que mirar el stock."""
    sembrar(api)

    # La yerba arranca en 48, se venden 1 (mostrador) y 4 (fiada), y entran
    # 24 por la recepción de compra confirmada: 48 - 5 + 24 = 67.
    #
    # 🔴 El número no se ajustó a mano hasta que diera: cada término
    # corresponde a un paso del seed, y si mañana cambia uno hay que volver a
    # hacer la cuenta. Que la recepción SUME es la mitad del test — una
    # recepción confirmada que no entrara stock sería una recepción de mentira.
    from scripts.seed_demo import _existencia

    items = {i["name"]: i["id"] for i in api.get("/catalog/items")}
    total = _existencia(api, items["Yerba mate 1 kg"], _salon(api))

    assert total == 48 - 5 + 24, f"la cuenta no cierra: quedó {total}"


def test_hay_ventas_en_mas_de_un_estado(api):
    """Una cancelada entre las confirmadas: la columna de estado del listado
    existe para eso, y con todas iguales se ve siempre lo mismo."""
    sembrar(api)

    estados = {v.get("status") or v.get("estado") for v in _ventas(api)}
    assert len(estados) >= 2, f"un solo estado: {estados}"


# ── 🔴 Stock que no está todo abastecido ──────────────────────────────────

def test_queda_un_articulo_sin_stock(api):
    """La pantalla de faltantes existe para eso."""
    sembrar(api)

    from scripts.seed_demo import _existencia

    items = {i["name"]: i["id"] for i in api.get("/catalog/items")}

    assert _existencia(api, items["Cerveza rubia 473 cc"], _salon(api)) == 0


def test_queda_stock_fraccionado(api):
    """El queso se carga en 14,5 kg. Si el producto redondeara, se vería acá."""
    sembrar(api)

    from scripts.seed_demo import _existencia

    items = {i["name"]: i["id"] for i in api.get("/catalog/items")}
    total = _existencia(api, items["Queso cremoso"], _salon(api))

    assert total != int(total), f"el stock quedó entero: {total}"


# ── Idempotencia ──────────────────────────────────────────────────────────

def test_correrlo_dos_veces_no_duplica(api, capsys):
    sembrar(api)
    capsys.readouterr()

    sembrar(api)

    salida = capsys.readouterr().out
    assert "artículos    0 creados, 11 ya estaban" in salida
    assert len(api.get("/catalog/items")) == 11
    assert len(api.get("/customers")) == 4


def test_la_segunda_corrida_no_agrega_ventas(api):
    sembrar(api)
    antes = len(_ventas(api))

    sembrar(api)

    assert len(_ventas(api)) == antes


# ── La guarda ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://demo.ventalibra.com.ar",
    "https://dev.ventalibra.com.ar",
    "http://127.0.0.1:8000",
])
def test_donde_si_se_puede_sembrar(url):
    assert url_no_productiva(url) is True


@pytest.mark.parametrize("url", [
    "https://ventalibra.com.ar",
    "https://cliente.ventalibra.com.ar",
    "https://demoliciones.ventalibra.com.ar",
])
def test_donde_NO(url):
    assert url_no_productiva(url) is False
