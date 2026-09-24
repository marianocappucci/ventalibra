"""El cobro con QR de MercadoPago en el mostrador, y la factura que sale sola.

Portado a la capa ERP (F3, ADR-025 D2: "el modelo de la familia" -- venta
PENDIENTE + `acreditar_pago_qr`, en vez del QR sobre un borrador propio con
`sale_mp_orders`). Las rutas nuevas son las del motor
(`libracore.ventas_cobro_router`, montado en `/api/ventas`).

`/sales` se retiró entero en F4 (2026-09-15, mismo ADR): las rutas del QR
viejo (`/sales/{id}/mp-qr`, `.../mp-status`) y el "camino legado" que este
archivo probaba contra `sale_mp_orders` sembrada a mano se fueron con el
router -- D2 nunca escribió esa tabla para una venta nueva (0 filas en
dev/demo), así que no queda nada que leer por ese camino: se retira la
sección entera, no se porta. `GET /sales/mp/estado` -- si el POS puede
cobrar por QR -- se movió a `GET /pos/mp-estado` (`app/routers/
ventas_extra.py`): mismo criterio (`app/services/mp_qr.py::esta_configurado`),
afuera de `/sales`.

Nada de esto habla con MercadoPago: `libracore.mp_api` se reemplaza por dobles
que registran con qué se los llamó. Lo que se mide acá es **este** producto —
qué monto y qué líneas se ponen en el QR, cuándo se sella el `payment_id`,
cuándo sale la factura y cuándo no.

🔑 El cliente REST en sí ya tiene sus propios tests en el repo de LibraCore
(`tests/test_mp_api.py`), incluida la URL de la orden, que estuvo mal durante
meses. Repetirlos acá mediría dos veces lo mismo y ninguna de las dos contra
MercadoPago.

**Las credenciales y el toggle de la automática (`/api/config/mercadopago`,
`libracore.mp_config_router`) no son parte de la capa ERP** -- ya vivían en el
motor desde antes de F3 y no dependen de cómo se registra una venta. Esos
tests (7) quedan intactos.
"""
import pytest
from libracore import config_manager, mp_api
from ventas_helpers import abrir_turno, crear_item, hoy

from app.services import mp_qr

# ── Arnés ────────────────────────────────────────────────────────────────


def _make_item(client, name="Fideos 500g", price="1500.00"):
    return crear_item(client, name=name, price=price)


def _venta_pendiente_con_qr(client, cantidad="2", price="1500.00"):
    """Registra una venta con un pago 'mercadopago' pendiente (D2): nace
    PENDIENTE (nadie escaneó todavía) y lista para ponerle el monto al QR de
    la caja."""
    item_id = _make_item(client, price=price)
    abrir_turno(client)
    total = float(cantidad) * float(price)
    creada = client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": float(cantidad), "precio": float(price),
                  "producto_id": item_id}],
        "pagos": [{"medio": "mercadopago", "monto": total, "cobrar_con_qr": True}],
    })
    assert creada.status_code == 200, creada.text
    venta = creada.json()
    assert venta["estado"] == "pendiente", venta
    return venta["id"], total


#: Las credenciales las sirve `libracore.mp_config_router` desde el 2026-08-30,
#: en `/api/config/mercadopago`. El endpoint propio que vivia en
#: `/settings/mercadopago` devolvia el ACCESS TOKEN EN CLARO; el del motor lo
#: devuelve enmascarado. Escribe las MISMAS claves de `config.json`, asi que
#: `mp_qr` y el POS no se enteran.
RUTA_MP = "/api/config/mercadopago"


def _configurar_mp(client, auto_facturar=False):
    guardada = client.put(RUTA_MP, json={
        "mp_access_token": "APP_USR-token-de-prueba",
        "mp_user_id": "123456789",
        "mp_pos_id": "CAJA01",
        "mp_auto_facturar_ventas": auto_facturar,
    })
    assert guardada.status_code == 200, guardada.text
    return guardada.json()


class _MpFalso:
    """Doble de `libracore.mp_api` que guarda con qué lo llamaron.

    🔑 Guarda **todas** las llamadas, no la última: la mitad de estos tests
    miden justamente que una segunda llamada NO ocurra.
    """

    def __init__(self):
        self.ordenes = []
        self.busquedas = []
        self.bajas = []
        #: Lo que devuelve `buscar_pago_por_referencia`. `None` = todavía nadie
        #: escaneó el QR.
        self.pago = None

    def instalar(self, monkeypatch):
        async def crear_orden_qr(**kwargs):
            self.ordenes.append(kwargs)
            # MercadoPago contesta 204 sin cuerpo: el cliente devuelve `{}`.
            return {}

        async def buscar_pago_por_referencia(external_reference, access_token):
            self.busquedas.append(external_reference)
            return self.pago

        async def eliminar_orden_qr(user_id, pos_id, access_token):
            self.bajas.append((user_id, pos_id))

        monkeypatch.setattr(mp_api, "crear_orden_qr", crear_orden_qr)
        monkeypatch.setattr(mp_api, "buscar_pago_por_referencia", buscar_pago_por_referencia)
        monkeypatch.setattr(mp_api, "eliminar_orden_qr", eliminar_orden_qr)
        return self


@pytest.fixture
def mp(monkeypatch):
    return _MpFalso().instalar(monkeypatch)


# ── Sin configurar ───────────────────────────────────────────────────────
# (config del motor, no de la capa ERP -- ver docstring del módulo: 7 tests intactos)


def test_sin_credenciales_el_pos_sabe_que_no_puede_cobrar_por_qr(admin_client):
    estado = admin_client.get("/pos/mp-estado")
    assert estado.status_code == 200, estado.text
    assert estado.json() == {"disponible": False, "auto_facturar": False}


def test_un_cajero_tambien_puede_leer_mp_estado(staff_client):
    """A diferencia de `/api/config/mercadopago` (admin-only), esto lo lee el
    cajero que arma el POS: decide si le ofrece el botón de QR."""
    assert staff_client.get("/pos/mp-estado").status_code == 200


def test_mp_estado_no_se_cae_sin_el_modulo_de_facturacion(admin_client):
    """Cobrar por QR no depende del plan de facturación (ADR-009): el gate
    de `/pos/mp-estado` es sólo de rol, sin `require_module`.

    Configura ANTES de apagar el módulo: `PUT /api/config/mercadopago` sí
    está gateado por `facturacion` (es la pantalla de Configuración, admin) --
    apagarlo primero daría 403 en el paso de armado, no en lo que se mide."""
    _configurar_mp(admin_client, auto_facturar=True)
    admin_client.app.state.modules.set_enabled("facturacion", False)

    estado = admin_client.get("/pos/mp-estado")
    assert estado.status_code == 200, estado.text
    # Prometería una factura que el plan no deja emitir.
    assert estado.json() == {"disponible": True, "auto_facturar": False}


def test_falta_user_id_o_pos_id_y_sigue_sin_estar_configurado(admin_client):
    """El token solo no alcanza: el user id va en la URL y el pos id en la caja.

    Sin esta comprobación, una instancia a medio configurar pasaría el chequeo
    y MercadoPago devolvería un 404 que no dice qué falta.

    🔴 Se afirma sobre `mp_qr.esta_configurado()` con el usuario actual, igual
    que hace `/pos/mp-estado`. Sin usuario no se puede resolver la caja activa.
    """
    # El admin de bootstrap tiene id 1.
    for faltante in ("mp_user_id", "mp_pos_id"):
        datos = {
            "mp_access_token": "APP_USR-x", "mp_user_id": "1", "mp_pos_id": "CAJA01",
            "mp_auto_facturar_ventas": False,
        }
        datos[faltante] = ""
        guardada = admin_client.put(RUTA_MP, json=datos)
        assert guardada.status_code == 200, guardada.text
        assert mp_qr.esta_configurado(1) is False, faltante

    # Control positivo: con token, user id y pos id (via config en caja única)
    # sí queda configurado.
    admin_client.put(RUTA_MP, json={
        "mp_access_token": "APP_USR-x", "mp_user_id": "1", "mp_pos_id": "CAJA01",
        "mp_auto_facturar_ventas": False,
    })
    assert mp_qr.esta_configurado(1) is True


def test_el_token_vacio_NO_borra_el_que_estaba(admin_client):
    """🔴 Es la diferencia de contrato con el endpoint propio que se fue.

    La pantalla muestra el token **enmascarado**, no el token. Si mandar el
    campo vacio lo borrara, guardar el POS ID desconectaria la cuenta sin que
    nadie lo pidiera. Vacio significa "no lo toques", igual que la contrasena
    de SMTP.
    """
    _configurar_mp(admin_client)
    admin_client.put(RUTA_MP, json={
        "mp_access_token": "", "mp_user_id": "123456789", "mp_pos_id": "CAJA02",
    })
    assert config_manager.load()["mp_access_token"] == "APP_USR-token-de-prueba"
    assert config_manager.load()["mp_pos_id"] == "CAJA02"
    assert mp_qr.esta_configurado() is True


def test_para_desconectar_la_cuenta_hay_una_puerta_propia(admin_client):
    """Con "vacio = no lo toques" no habria otra forma de sacar el token, y el
    comercio quedaria atado a la cuenta que cargo la primera vez."""
    _configurar_mp(admin_client)
    r = admin_client.delete(f"{RUTA_MP}/credenciales")
    assert r.status_code == 200, r.text
    assert config_manager.load()["mp_access_token"] == ""
    assert mp_qr.esta_configurado() is False


def test_el_token_no_vuelve_en_claro_por_la_API(admin_client):
    """El endpoint propio lo devolvia entero en el JSON de una pantalla."""
    _configurar_mp(admin_client)
    visible = admin_client.get(RUTA_MP).json()
    assert visible["mp_access_token"] != "APP_USR-token-de-prueba"
    assert visible["mp_access_token_cargado"] is True


def test_guardar_mercadopago_no_borra_el_resto_de_la_configuracion(admin_client):
    """🔴 `config_manager.save()` mergea contra los DEFAULTS: guardar un dict
    con sólo las claves de MercadoPago dejaría empresa, SMTP y ticket en su
    valor por defecto. El PUT contestaría 200 y la pérdida recién se notaría al
    imprimir un ticket."""
    guardado = admin_client.put("/settings/ticket", json={
        "ancho_mm": "58", "fuente_size": 11, "mostrar_logo": True,
        "linea_corte": False, "pie": "Gracias por su compra",
    })
    assert guardado.status_code == 200, guardado.text

    _configurar_mp(admin_client)

    ticket = admin_client.get("/settings/ticket").json()
    assert ticket["ancho_mm"] == "58"
    assert ticket["pie"] == "Gracias por su compra"
    assert ticket["fuente_size"] == 11


def test_el_toggle_de_la_automatica_sobrevive_a_recargar_la_config(admin_client):
    """`mp_auto_facturar_ventas` no está en los DEFAULTS de LibraCore: viaja
    como `extra_defaults`. Leerla con un `load()` pelado la perdería."""
    _configurar_mp(admin_client, auto_facturar=True)
    assert admin_client.get(RUTA_MP).json()["mp_auto_facturar_ventas"] is True
    assert mp_qr.auto_facturar_prendida() is True
    # Y el `config.json` en disco lo tiene de verdad, no sólo el default en
    # memoria: se lee con el `load()` genérico, sin los extra_defaults.
    assert config_manager.load().get("mp_auto_facturar_ventas") is True


# ── La orden en la caja ──────────────────────────────────────────────────


def test_sin_credenciales_poner_el_monto_en_el_qr_da_400_y_dice_que_falta(admin_client, mp):
    vid, _ = _venta_pendiente_con_qr(admin_client)
    respuesta = admin_client.post(f"/api/ventas/{vid}/mp-qr")
    assert respuesta.status_code == 400, respuesta.text
    detalle = respuesta.json()["detail"]
    # El mensaje nombra Access Token y User ID (a nivel instancia). El POS ID
    # vive en la caja y se valida en un paso posterior con 422.
    assert "Access Token" in detalle and "User ID" in detalle
    assert mp.ordenes == []


def test_poner_el_monto_manda_el_total_las_lineas_y_las_tres_credenciales(admin_client, mp):
    _configurar_mp(admin_client)
    vid, total = _venta_pendiente_con_qr(admin_client, cantidad="2", price="1500.00")

    respuesta = admin_client.post(f"/api/ventas/{vid}/mp-qr")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["total"] == 3000.0

    assert len(mp.ordenes) == 1
    orden = mp.ordenes[0]
    assert orden["user_id"] == "123456789"
    assert orden["pos_id"] == "CAJA01"
    assert orden["access_token"] == "APP_USR-token-de-prueba"
    assert orden["total"] == 3000.0
    assert orden["external_reference"] == f"venta-{vid}"
    # Las líneas van con el precio FINAL, que es lo que el cliente ve al
    # escanear. El desglose de IVA es de la factura, no del cobro.
    #
    # 🔴 libracommerce v0.16.2 agrega `id` (el de `sale_items`) a cada línea
    # de `GET /api/ventas/{vid}` -- de donde sale `venta["items"]` acá. Se
    # compara sin esa clave en vez de por igualdad estricta del dict, para no
    # quedar atado a qué otras columnas sume el motor a futuro.
    item = dict(orden["items"][0])
    item.pop("id", None)
    assert item == {
        "producto_id": orden["items"][0]["producto_id"],
        "variante_id": None,
        "nombre": "línea",
        "qty": 2.0,
        "precio": 1500.0,
        "subtotal": 3000.0,
    }


# 🔴 **Retirado, invariante ya no aplica**: `test_cada_intento_usa_una_referencia_distinta`
# probaba que la referencia (`sale_mp_orders.external_reference`) se renovaba en cada intento --
# necesario en el modelo viejo porque el borrador se podía seguir editando entre un intento de
# QR y el siguiente (otro monto, mismo `sale_id`). D2 usa una referencia FIJA y determinística,
# `venta-{vid}` (`libracore.ventas_cobro_router.venta_mp_qr`), sin tabla de "intentos": no hace
# falta reemplazarla porque la venta ya no cambia de monto después de creada (D1, atómica) -- no
# hay "el intento siguiente puede ser por otra plata" que evitar.

# 🔴 **Retirado, invariante ya no aplica**: `test_un_borrador_vacio_no_se_puede_poner_en_el_qr`
# probaba el 502 de poner el monto sobre un borrador SIN líneas. D1 no admite crear una venta sin
# ítems (`POST /api/ventas` -- 422, ver `tests/test_sales.py::test_confirm_without_items_fails`):
# no puede existir una venta "pendiente y vacía" a la que ponerle el QR.


def test_si_mercadopago_rechaza_la_orden_el_poll_no_encuentra_nada_que_esperar(admin_client, mp, monkeypatch):
    """🔴 **Invariante cambiado, no retirado.** El modelo viejo distinguía "todavía no puse el
    QR" (`sin_orden`) de "lo puse y nadie pagó" (`pending`), porque guardaba una fila por
    intento (`sale_mp_orders`). D2 no guarda nada de eso -- la referencia es determinística
    (`venta-{vid}`) y el poll simplemente le pregunta a MercadoPago por ella exista o no una
    orden puesta. Sin orden, la búsqueda no encuentra nada (`self.pago` sigue en `None`) y el
    poll da el mismo `pending` que "todavía nadie escaneó": las dos situaciones colapsan en un
    solo estado, que es lo que se afirma acá."""
    _configurar_mp(admin_client)
    vid, _ = _venta_pendiente_con_qr(admin_client)

    async def explota(**kwargs):
        raise RuntimeError("MP QR error 404: {'message': 'pos not found'}")

    monkeypatch.setattr(mp_api, "crear_orden_qr", explota)
    respuesta = admin_client.post(f"/api/ventas/{vid}/mp-qr")
    assert respuesta.status_code == 502, respuesta.text
    assert "404" in respuesta.json()["detail"]

    estado = admin_client.get(f"/api/ventas/{vid}/mp-status")
    assert estado.json()["status"] == "pending"


# 🔴 **Retirado, invariante ya no aplica**: `test_bajar_del_qr_saca_la_orden_de_la_caja` probaba
# `DELETE /sales/{id}/mp-qr`. La factory del motor (`libracore.ventas_cobro_router.build_cobro_
# de_ventas_router`) no tiene ruta de "bajar del QR": según el propio `app/routers/sales.py`
# ("410: no hay equivalente de 'bajar del QR' en el modelo nuevo -- D2: la venta pendiente se
# acredita o se abandona; el cartel es fijo por caja"), no hay nada que "bajar" -- una venta
# pendiente que nadie paga se queda pendiente (o se anula), no se le saca el monto del cartel de
# MercadoPago.


# ── El poll ──────────────────────────────────────────────────────────────


def test_mientras_nadie_escanee_el_poll_dice_pendiente(admin_client, mp):
    _configurar_mp(admin_client)
    vid, _ = _venta_pendiente_con_qr(admin_client)
    admin_client.post(f"/api/ventas/{vid}/mp-qr")

    estado = admin_client.get(f"/api/ventas/{vid}/mp-status")
    assert estado.status_code == 200, estado.text
    # 🔴 Ya no viene `payment_id: None` -- el motor sólo pone la clave cuando
    # hay algo que informar (ver `libracore.ventas_cobro_router.venta_mp_status`).
    assert estado.json() == {"status": "pending"}


def test_un_pago_rechazado_no_acredita_nada(admin_client, mp):
    _configurar_mp(admin_client)
    vid, _ = _venta_pendiente_con_qr(admin_client)
    admin_client.post(f"/api/ventas/{vid}/mp-qr")
    mp.pago = {"id": 999, "status": "rejected"}

    estado = admin_client.get(f"/api/ventas/{vid}/mp-status")
    assert estado.json() == {"status": "rejected"}
    assert admin_client.get(f"/api/ventas/{vid}").json()["estado"] == "pendiente"


def test_el_poll_sella_el_payment_id_y_deja_de_preguntarle_a_mercadopago(admin_client, mp):
    _configurar_mp(admin_client)
    vid, _ = _venta_pendiente_con_qr(admin_client)
    admin_client.post(f"/api/ventas/{vid}/mp-qr")
    mp.pago = {"id": 112233, "status": "approved"}

    primera = admin_client.get(f"/api/ventas/{vid}/mp-status")
    assert primera.json()["status"] == "approved"
    assert primera.json()["payment_id"] == "112233"
    assert len(mp.busquedas) == 1

    # El POS pollea cada 3 segundos: el segundo tick tiene que salir de la
    # fila ya sellada y no de otra consulta a MercadoPago.
    segunda = admin_client.get(f"/api/ventas/{vid}/mp-status")
    assert segunda.json()["status"] == "approved"
    assert segunda.json()["payment_id"] == "112233"
    assert len(mp.busquedas) == 1

    # Y la venta quedó cobrada -- D2, `acreditar_pago_qr` recalcula el estado.
    assert admin_client.get(f"/api/ventas/{vid}").json()["estado"] == "cobrada"


def test_con_el_pago_acreditado_no_se_puede_rotar_la_referencia(admin_client, mp):
    """Cerrado en libracore v1.101.0: `venta_mp_qr` da 409 sin llamar a
    MercadoPago si la venta ya tiene `mp_payment_id` -- pedir de nuevo una
    plata que ya entró."""
    _configurar_mp(admin_client)
    vid, _ = _venta_pendiente_con_qr(admin_client)
    admin_client.post(f"/api/ventas/{vid}/mp-qr")
    mp.pago = {"id": 112233, "status": "approved"}
    admin_client.get(f"/api/ventas/{vid}/mp-status")

    respuesta = admin_client.post(f"/api/ventas/{vid}/mp-qr")
    assert respuesta.status_code == 409, respuesta.text
    assert len(mp.ordenes) == 1


def test_una_venta_anulada_no_puede_pedir_el_qr(admin_client, mp):
    """Cerrado en libracore v1.101.0: `venta_mp_qr` da 409 sin llamar a
    MercadoPago si la venta está anulada -- pedir plata por algo que ya no
    existe."""
    _configurar_mp(admin_client)
    vid, _ = _venta_pendiente_con_qr(admin_client)
    anulada = admin_client.post(f"/api/ventas/{vid}/anular")
    assert anulada.status_code == 200, anulada.text

    respuesta = admin_client.post(f"/api/ventas/{vid}/mp-qr")
    assert respuesta.status_code == 409, respuesta.text
    assert mp.ordenes == []


def test_mp_status_sobre_una_venta_anulada_no_factura(admin_client, mp):
    """Cerrado en libracore v1.101.0: la plata puede entrar en MercadoPago
    DESPUÉS de que el cajero anuló la venta -- `venta_mp_status` no la
    acredita ni la factura, devuelve `\"anulada\"` para que alguien la
    devuelva a mano."""
    _configurar_mp(admin_client, auto_facturar=True)
    vid, _ = _venta_pendiente_con_qr(admin_client)
    admin_client.post(f"/api/ventas/{vid}/mp-qr")

    anulada = admin_client.post(f"/api/ventas/{vid}/anular")
    assert anulada.status_code == 200, anulada.text

    mp.pago = {"id": 998877, "status": "approved"}
    estado = admin_client.get(f"/api/ventas/{vid}/mp-status")
    assert estado.json()["status"] == "anulada"
    assert estado.json()["payment_id"] == "998877"

    venta = admin_client.get(f"/api/ventas/{vid}").json()
    assert venta["estado"] == "anulada"
    assert venta["factura_id"] is None


# ── El cobro por QR y la factura ──────────────────────────────────────────


def _cobrar_el_qr(client, mp, vid, payment_id=112233):
    client.post(f"/api/ventas/{vid}/mp-qr")
    mp.pago = {"id": payment_id, "status": "approved"}
    estado = client.get(f"/api/ventas/{vid}/mp-status")
    assert estado.json()["status"] == "approved", estado.text
    return estado.json()


def test_cobrar_por_qr_sella_el_payment_id_en_la_linea_de_pago(admin_client, mp):
    """🔴 **Invariante cambiado, no retirado.** No hay más un `confirm` aparte que selle la
    referencia: D2 acredita y sella en el MISMO paso (`GET /mp-status`, que es un GET con
    efectos -- ver su docstring). Y el formato cambia: `MP#<payment_id>` (`libracommerce.erp.
    ventas.acreditar_pago_qr`), no `mp-<payment_id>` (el del modelo viejo)."""
    _configurar_mp(admin_client)
    vid, _ = _venta_pendiente_con_qr(admin_client)
    _cobrar_el_qr(admin_client, mp, vid)

    venta = admin_client.get(f"/api/ventas/{vid}").json()
    pagos = venta["pagos"]
    assert len(pagos) == 1
    assert pagos[0]["referencia"] == "MP#112233"


def test_una_referencia_que_manda_el_pos_no_se_pisa(admin_client, mp):
    """Cerrado en libracommerce v0.16.2: `acreditar_pago_qr` sólo completa la
    referencia si está vacía o NULL -- una referencia que el mostrador ya
    cargó a mano (un lote, un comprobante) sobrevive a acreditarse por QR."""
    _configurar_mp(admin_client)
    item_id = _make_item(admin_client)
    abrir_turno(admin_client)
    creada = admin_client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": 2, "precio": 1500.0, "producto_id": item_id}],
        "pagos": [{"medio": "mercadopago", "monto": 3000.0, "cobrar_con_qr": True,
                  "referencia": "lote-77"}],
    })
    assert creada.status_code == 200, creada.text
    vid = creada.json()["id"]

    _cobrar_el_qr(admin_client, mp, vid)
    venta = admin_client.get(f"/api/ventas/{vid}").json()
    assert venta["pagos"][0]["referencia"] == "lote-77"


# 🔴 **Retirado, invariante ya no aplica**: `test_una_venta_en_efectivo_no_se_lleva_la_
# referencia_del_qr` probaba que, tras poner el monto en el QR sobre un borrador, CONFIRMAR esa
# misma venta en efectivo (en vez de esperar el QR) no le pegaba la referencia sellada. D1 borró
# esa posibilidad: el medio de pago de una venta se fija al registrarla (`POST /api/ventas`, una
# sola vez) y no se puede "decidir después" que en realidad se cobró de otra forma -- no hay un
# borrador con un QR puesto al que se le pueda cambiar de opinión y confirmar distinto. Cobrar en
# efectivo es directamente OTRA venta, sin relación con ningún QR.


def test_con_la_automatica_prendida_la_venta_sale_facturada_sin_pedirlo(admin_client, mp):
    """El POS no pide facturar: la decisión es del backend (`mp-status`, que llama a
    `facturar_si_esta_prendida` en el mismo paso que acredita)."""
    _configurar_mp(admin_client, auto_facturar=True)
    vid, _ = _venta_pendiente_con_qr(admin_client)
    estado = _cobrar_el_qr(admin_client, mp, vid)

    assert estado["factura_id"] is not None
    venta = admin_client.get(f"/api/ventas/{vid}").json()
    assert venta["factura_id"] == estado["factura_id"]


def test_sin_la_automatica_el_mismo_cobro_no_factura(admin_client, mp):
    """El control negativo del test de arriba: con la automática apagada, el mismo camino tiene
    que dejar la venta sin comprobante."""
    _configurar_mp(admin_client, auto_facturar=False)
    vid, _ = _venta_pendiente_con_qr(admin_client)
    estado = _cobrar_el_qr(admin_client, mp, vid)

    assert estado["factura_id"] is None
    assert admin_client.get(f"/api/ventas/{vid}").json()["factura_id"] is None


def test_la_automatica_no_factura_una_venta_que_no_se_cobro_por_qr(admin_client):
    """La automática es del cobro con QR, no un "facturar todo": una venta en efectivo con el
    toggle prendido sigue sin comprobante."""
    _configurar_mp(admin_client, auto_facturar=True)
    item_id = _make_item(admin_client)
    abrir_turno(admin_client)
    venta = admin_client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": 2, "precio": 1500.0, "producto_id": item_id}],
        "pagos": [{"medio": "efectivo", "monto": 3000.0}],
    })
    assert venta.status_code == 200, venta.text
    assert venta.json()["factura_id"] is None


def test_sin_el_modulo_de_facturacion_el_cobro_por_qr_no_se_cae(admin_client, mp):
    """La automática no puede convertir un cobro en un 403.

    Una instancia con un plan sin facturación tiene que poder cobrar igual: la
    venta se confirma y queda sin comprobante, que es lo que el plan dice.
    """
    _configurar_mp(admin_client, auto_facturar=True)
    # El plan se aplica sobre el repositorio, no por HTTP: no hay endpoint
    # para apagar un módulo — lo hace `plans.aplicar_plan_en_db()` al
    # provisionar. Mismo mecanismo que usa `tests/test_modules.py`.
    admin_client.app.state.modules.set_enabled("facturacion", False)

    vid, _ = _venta_pendiente_con_qr(admin_client)
    estado = _cobrar_el_qr(admin_client, mp, vid)

    assert admin_client.get(f"/api/ventas/{vid}").json()["estado"] == "cobrada"
    assert estado["factura_id"] is None


# 🔴 **Retirado en F4 (2026-09-15, ADR-025), no portado**: el "camino LEGADO"
# probaba `GET /sales/{id}/mp-status` (`app/services/mp_qr.py::estado_del_cobro`,
# con `orden_vigente`/`orden_acreditada`) sembrando una fila de `sale_mp_orders`
# a mano -- el modelo viejo, antes de D2. Con `/sales` retirado entero no queda
# ninguna ruta que ejercite ese código, y D2 nunca escribe esa tabla para una
# venta nueva (0 filas en dev/demo, mismo hallazgo que
# `tests/test_cobros_sin_venta.py`, retirado junto con el aviso que probaba):
# no hay nada vivo que este archivo deba seguir cubriendo. `estado_del_cobro`,
# `orden_vigente`, `orden_acreditada` y `MpError` se borraron de
# `app/services/mp_qr.py` -- la tabla `sale_mp_orders` NO se borra.
