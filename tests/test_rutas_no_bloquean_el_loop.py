"""Las rutas del cobro por QR no frenan el loop de uvicorn.

🔴 VentaLibra corre uvicorn con **un solo proceso**. Una ruta `async def` que
llama sincronico a la base frena el loop entero mientras dura: ningun otro
request avanza, `/health` incluido. En un test comun no se ve, porque la ruta
contesta bien: lo que hace mal es retener a los demas. Aca se mide eso y nada
mas.

Como: una llamada de cada ruta se reemplaza por una que duerme con
`time.sleep` --bloquea el hilo donde corre, como la consulta real-- y, mientras
duerme, se pide `/health` por el **mismo loop**. Si la ruta corre fuera del
loop, `/health` termina antes de que la llamada lenta se despierte; si lo
bloquea, `/health` no puede ni empezar hasta entonces. Se compara contra el
instante en que la llamada lenta **se desperto**, no contra un umbral de
tiempo, asi que el resultado no depende de lo rapida que sea la maquina.

🔑 Lo lento va **adentro** de la corrutina de `services/mp_qr.py` (el cliente
de MercadoPago), que mezcla la red asincronica con la base sincronica: pasar la
ruta a `def` sin sacar esa corrutina del loop de uvicorn dejaria el test en
rojo igual.

Es la misma medicion que `tests/test_rutas_no_bloquean_el_loop.py` de
Contalibra, Restolibra y LibraCore. Cada test se probo contra la ruta como
estaba en `origin/develop`: se ponen rojos.
"""
import asyncio
import threading
import time

import httpx
import pytest
from libracore import arca_facturacion, mp_api
from test_mp_qr import _borrador_con_item, _configurar_mp, _MpFalso

#: Lo que duerme la llamada reemplazada. Alcanza con que sea mucho mas que lo
#: que tarda un `/health` sin carga.
LENTO = 0.5

#: El mismo host que `conftest.https_client`: la cookie de sesion es `Secure`
#: y httpx no la reenvia sobre http plano ni a un host sin punto.
BASE_URL = "https://ventalibra.test"


class _Lento:
    """Una llamada sincronica que tarda.

    `time.sleep` y no `asyncio.sleep` es el punto entero: una consulta a la
    base no le cede el control a nadie.
    """

    def __init__(self):
        self.entro = threading.Event()
        self.desperto_en: float | None = None

    def dormir(self):
        self.entro.set()
        time.sleep(LENTO)
        if self.desperto_en is None:
            self.desperto_en = time.monotonic()


def _mientras_duerme(client, lento: _Lento, pedir):
    """Corre `pedir(cliente)` con la sesion de `client` y, con la llamada lenta
    ya adentro, un `/health` anonimo por el MISMO loop.

    Devuelve la respuesta del pedido, la de `/health` y el instante en que
    `/health` termino.
    """

    async def _correr():
        transporte = httpx.ASGITransport(app=client.app)
        async with (
            httpx.AsyncClient(transport=transporte, base_url=BASE_URL,
                              cookies=client.cookies) as quien_pide,
            httpx.AsyncClient(transport=transporte, base_url=BASE_URL) as anonimo,
        ):
            tarea = asyncio.create_task(pedir(quien_pide))
            # La espera va a un hilo para no ocupar el loop con la espera misma.
            assert await asyncio.to_thread(lento.entro.wait, 10), (
                "la llamada lenta nunca empezo: el parche no intercepta la ruta")
            health = await anonimo.get("/health")
            health_termino = time.monotonic()
            respuesta = await asyncio.wait_for(tarea, 30)
        return respuesta, health, health_termino

    return asyncio.run(_correr())


def _no_bloqueo(lento: _Lento, health, health_termino: float):
    assert health.status_code == 200, health.text
    # Sin esto el test pasaria si el parche no interceptara nada: sin llamada
    # lenta, no hay nada que bloquee.
    assert lento.desperto_en is not None, "la parte lenta no llego a correr"
    assert health_termino < lento.desperto_en, (
        f"/health termino {health_termino - lento.desperto_en:.2f}s DESPUES de "
        "que se despertara la llamada lenta: la ruta bloqueo el loop mientras dormia"
    )


# ── Las tres rutas del QR ────────────────────────────────────────────────

#: Ruta -> (metodo, sufijo, funcion de `mp_api` que se vuelve lenta, lo que
#: devuelve, status esperado). La lenta es la llamada a MercadoPago, que es
#: corrutina: entre medio, `services/mp_qr.py` lee y escribe la base.
RUTAS_DEL_QR = {
    "poner_en_el_qr": ("POST", "mp-qr", "crear_orden_qr", {}, 200),
    "bajar_del_qr": ("DELETE", "mp-qr", "eliminar_orden_qr", None, 204),
    # La que mas pesa: el POS la pollea cada 3 segundos mientras el cliente
    # escanea.
    "estado_del_qr": ("GET", "mp-status", "buscar_pago_por_referencia",
                      {"id": 77, "status": "approved"}, 200),
}


@pytest.mark.parametrize("ruta", list(RUTAS_DEL_QR))
def test_las_rutas_del_qr_no_frenan_el_loop(admin_client, monkeypatch, ruta):
    metodo, sufijo, funcion, devuelve, esperado = RUTAS_DEL_QR[ruta]
    _MpFalso().instalar(monkeypatch)
    _configurar_mp(admin_client)
    sale_id, _ = _borrador_con_item(admin_client)
    if ruta != "poner_en_el_qr":
        # Bajarla o pollearla necesita una orden puesta, y se pone con el doble
        # rapido: lo lento es solo lo que se mide.
        puesta = admin_client.post(f"/sales/{sale_id}/mp-qr")
        assert puesta.status_code == 200, puesta.text

    lento = _Lento()

    async def mercadopago_lento(*args, **kwargs):
        lento.dormir()
        return devuelve

    monkeypatch.setattr(mp_api, funcion, mercadopago_lento)

    respuesta, health, fin = _mientras_duerme(
        admin_client, lento, lambda c: c.request(metodo, f"/sales/{sale_id}/{sufijo}"))

    assert respuesta.status_code == esperado, respuesta.text
    if ruta == "estado_del_qr":
        assert respuesta.json() == {"status": "approved", "payment_id": "77"}
    _no_bloqueo(lento, health, fin)


# ── El confirm: sigue `async` a proposito, y este test lo deja escrito ────


@pytest.mark.xfail(
    strict=True, raises=AssertionError,
    reason=(
        "confirm_sale sigue async a proposito: como `def` dos confirmaciones de la "
        "MISMA venta dejan de estar serializadas sobre la conexion unica de "
        "`app.state.conn` y se pueden confirmar las dos (stock y factura dobles). "
        "Ver el comentario de la ruta. Cuando eso se resuelva, sacar este xfail."
    ),
)
def test_confirmar_con_factura_no_frena_el_loop(admin_client, monkeypatch):
    """🔴 Hoy SI frena el loop, y se sabe: es el pendiente de `confirm_sale`.

    Lo lento va adentro de la numeracion con ARCA, que es corrutina y en
    produccion firma el TRA con `openssl` por subproceso. `strict=True`: el dia
    que la ruta deje de frenar el loop este test pasa, el xfail se pone rojo, y
    obliga a sacar la marca en vez de dejar un pendiente que ya no existe.
    """
    sale_id, location_id = _borrador_con_item(admin_client)
    lento = _Lento()
    real = arca_facturacion.get_next_numero_with_arca

    async def numerar_con_openssl(punto_venta, tipo):
        lento.dormir()
        return await real(punto_venta, tipo)

    monkeypatch.setattr(arca_facturacion, "get_next_numero_with_arca", numerar_con_openssl)

    respuesta, health, fin = _mientras_duerme(admin_client, lento, lambda c: c.post(
        f"/sales/{sale_id}/confirm",
        json={"location_id": location_id, "medio_pago": "efectivo", "invoice": True},
    ))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["factura"] is not None, "la venta tenia que facturarse"
    _no_bloqueo(lento, health, fin)
