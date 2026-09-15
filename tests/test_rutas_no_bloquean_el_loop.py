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
from test_mp_qr import _configurar_mp, _MpFalso
from ventas_helpers import abrir_turno, con_stock, crear_item, deposito_default, registrar_venta


#: 🔴 Portado a F3 (2026-09-14, ADR-025). Antes armaba un borrador con
#: `_borrador_con_item` de `test_mp_qr.py` (`POST /sales` + `POST
#: /sales/{id}/items`, las dos retiradas -- 410 desde F3). Se arma ACÁ y NO se
#: importa de `test_mp_qr.py` a propósito: ese archivo lo está portando otro
#: agente en paralelo sobre el MISMO worktree, y su `_borrador_con_item` puede
#: estar a mitad de cambiar. `_configurar_mp` y `_MpFalso` sí se siguen
#: importando de ahí -- no tocan `/sales` en absoluto (van contra
#: `/api/config/mercadopago` y contra `libracore.mp_api`), así que no corren
#: ese riesgo.
#:
#: El modelo nuevo no tiene borrador (D1): la venta se registra completa, con
#: un pago `mercadopago` en `cobrar_con_qr=True` -- nace `PENDIENTE`, no toca
#: la caja, y es lo que después acredita el poll de `mp-status`.
def _venta_para_qr(client, cantidad="2", price="1500.00"):
    item_id = crear_item(client, price=price)
    location_id = deposito_default(client)
    con_stock(client, item_id, location_id, cantidad="50")
    abrir_turno(client)
    total = float(cantidad) * float(price)
    venta = registrar_venta(
        client, item_id, precio=price, cantidad=cantidad,
        pagos=[{"medio": "mercadopago", "monto": total, "cobrar_con_qr": True}],
    )
    return venta["id"], location_id

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


# ── Las rutas del QR ─────────────────────────────────────────────────────

#: Ruta -> (metodo, sufijo, funcion de `mp_api` que se vuelve lenta, lo que
#: devuelve, status esperado). La lenta es la llamada a MercadoPago, que es
#: corrutina: entre medio, el router del motor lee y escribe la base.
#:
#: 🔴 Portado a F3 (2026-09-14, ADR-025): antes eran TRES rutas bajo
#: `/sales/{id}/...` (`app/services/mp_qr.py`, propio de VentaLibra). Desde F3
#: el cobro por QR de una venta nueva vive en `libracore.ventas_cobro_router`,
#: montado como `/api/ventas/{vid}/...` (D2, `app/main.py`) -- y ese router
#: sólo tiene DOS rutas, no tres: `POST /mp-qr` y `GET /mp-status`. **No hay
#: "bajar del QR"** (`DELETE /mp-qr`) en el modelo nuevo -- el QR es fijo por
#: caja (el cartel impreso del mostrador) y lo que cambia es cuánto cobra al
#: escanearlo, no si hay o no un pedido "puesto"; ver el docstring de
#: `venta_mp_qr` en el motor. El invariante que probaba `bajar_del_qr` (esa
#: ruta no frena el loop) no tiene ruta que medir, así que se retira -- no se
#: reapunta a nada porque no hay equivalente.
RUTAS_DEL_QR = {
    "poner_en_el_qr": ("POST", "mp-qr", "crear_orden_qr", {}, 200),
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
    sale_id, _ = _venta_para_qr(admin_client)

    lento = _Lento()

    async def mercadopago_lento(*args, **kwargs):
        lento.dormir()
        return devuelve

    monkeypatch.setattr(mp_api, funcion, mercadopago_lento)

    respuesta, health, fin = _mientras_duerme(
        admin_client, lento, lambda c: c.request(metodo, f"/api/ventas/{sale_id}/{sufijo}"))

    assert respuesta.status_code == esperado, respuesta.text
    if ruta == "estado_del_qr":
        # `factura_id`: campo nuevo del router del motor (no existía en el
        # propio de VentaLibra) -- `None` porque `_configurar_mp` no prende
        # la automática por default.
        assert respuesta.json() == {"status": "approved", "payment_id": "77", "factura_id": None}
    _no_bloqueo(lento, health, fin)


# ── Facturar: pendiente vencido -- el xfail lo cerró la migración, no un fix ──
#
# 🔴 Hasta el 2026-09-14 este test estaba marcado `xfail(strict=True)`: el
# viejo `confirm_sale` (`POST /sales/{id}/confirm`) era `async def` y bloqueaba
# el loop mientras numeraba con ARCA (una corrutina que en producción firma el
# TRA con `openssl` por subproceso). Esa ruta quedó retirada (410) en F3
# (ADR-025) y el camino nuevo para facturar una venta es
# `POST /api/ventas/{vid}/facturar`, montado en `app/main.py` desde
# `libracore.ventas_cobro_router` -- que es un `def`, **no** `async def`, a
# propósito (ver el comentario de esa factory: "corren en el threadpool, lo
# asincrónico de verdad va con `asyncio.run` en un loop propio de ese hilo").
# El pendiente que el xfail describía no es que se haya corregido: es que la
# ruta que lo tenía ya no existe, y la que la reemplaza nació sin él. Sacar el
# xfail y medir la ruta nueva es lo que exige la nota de arriba: "el día que
# deje de frenar el loop [...] obliga a sacar la marca en vez de dejar un
# pendiente que ya no existe" -- ese día es hoy, por otra vía.
def test_facturar_no_frena_el_loop(admin_client, monkeypatch):
    item_id = crear_item(admin_client)
    location_id = deposito_default(admin_client)
    con_stock(admin_client, item_id, location_id)
    abrir_turno(admin_client)
    venta = registrar_venta(admin_client, item_id)
    sale_id = venta["id"]

    lento = _Lento()
    real = arca_facturacion.get_next_numero_with_arca

    async def numerar_con_openssl(punto_venta, tipo):
        lento.dormir()
        return await real(punto_venta, tipo)

    monkeypatch.setattr(arca_facturacion, "get_next_numero_with_arca", numerar_con_openssl)

    respuesta, health, fin = _mientras_duerme(
        admin_client, lento, lambda c: c.post(f"/api/ventas/{sale_id}/facturar"))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["factura"] is not None, "la venta tenia que facturarse"
    _no_bloqueo(lento, health, fin)
