"""El cobro con QR de MercadoPago en el mostrador, y la factura que sale sola.

Nada de esto habla con MercadoPago: `libracore.mp_api` se reemplaza por dobles
que registran con qué se los llamó. Lo que se mide acá es **este** producto —
qué monto y qué líneas se ponen en el QR, cuándo se sella el `payment_id`,
cuándo sale la factura y cuándo no.

🔑 El cliente REST en sí ya tiene sus propios tests en el repo de LibraCore
(`tests/test_mp_api.py`), incluida la URL de la orden, que estuvo mal durante
meses. Repetirlos acá mediría dos veces lo mismo y ninguna de las dos contra
MercadoPago.
"""
import pytest

from libracore import config_manager, mp_api

from app.services import mp_qr


# ── Arnés ────────────────────────────────────────────────────────────────


def _abrir_turno(client, monto_inicial=0):
    abierto = client.post("/shifts/open", json={"monto_inicial": monto_inicial})
    assert abierto.status_code == 200, abierto.text
    return abierto.json()["turno"]["id"]


def _make_item(client, name="Fideos 500g", price="1500.00"):
    client.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    created = client.post(
        "/catalog/items",
        json={"name": name, "unit_code": "u", "default_sale_price": price, "default_cost": "900.00"},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _make_location(client, name="Sucursal 1"):
    created = client.post("/locations", json={"name": name})
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _borrador_con_item(client, cantidad="2", price="1500.00"):
    """Un borrador con líneas, listo para ponerle el monto al QR."""
    item_id = _make_item(client, price=price)
    location_id = _make_location(client)
    client.post(
        "/stock/adjustments",
        json={"item_id": item_id, "location_id": location_id, "quantity_delta": "50"},
    )
    _abrir_turno(client)
    draft = client.post("/sales", json={})
    sale_id = draft.json()["id"]
    agregada = client.post(f"/sales/{sale_id}/items", json={"item_id": item_id, "quantity": cantidad})
    assert agregada.status_code == 200, agregada.text
    return sale_id, location_id


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


def test_sin_credenciales_el_pos_sabe_que_no_puede_cobrar_por_qr(admin_client):
    estado = admin_client.get("/sales/mp/estado")
    assert estado.status_code == 200, estado.text
    assert estado.json() == {"disponible": False, "auto_facturar": False}


def test_sin_credenciales_poner_el_monto_en_el_qr_da_400_y_dice_que_falta(admin_client, mp):
    sale_id, _ = _borrador_con_item(admin_client)
    respuesta = admin_client.post(f"/sales/{sale_id}/mp-qr")
    assert respuesta.status_code == 400, respuesta.text
    detalle = respuesta.json()["detail"]
    # El mensaje nombra los tres datos: un 400 que dijera "no configurado" no
    # le dice al operador dónde ir ni qué cargar.
    assert "Access Token" in detalle and "User ID" in detalle and "POS ID" in detalle
    assert mp.ordenes == []


def test_falta_uno_solo_de_los_tres_y_sigue_sin_estar_configurado(admin_client):
    """El token solo no alcanza: el user id y el pos id van en la URL.

    Sin esta comprobación, una instancia a medio configurar pasaría el chequeo
    y MercadoPago devolvería un 404 que no dice qué falta.

    🔴 Se afirma sobre `mp_qr.esta_configurado()` y no sobre la respuesta del
    endpoint. El router del motor no devuelve un `configurado`: ese calculo es
    del POS, y la pantalla lo repite del lado del cliente. Preguntarle al
    servicio es preguntarle a quien de verdad decide si el QR cobra.
    """
    for faltante in ("mp_user_id", "mp_pos_id"):
        datos = {
            "mp_access_token": "APP_USR-x", "mp_user_id": "1", "mp_pos_id": "CAJA01",
            "mp_auto_facturar_ventas": False,
        }
        datos[faltante] = ""
        guardada = admin_client.put(RUTA_MP, json=datos)
        assert guardada.status_code == 200, guardada.text
        assert mp_qr.esta_configurado() is False, faltante

    # Control positivo: con los tres cargados sí queda configurado. Sin esto,
    # un `esta_configurado()` que devolviera siempre False pasaría el test.
    admin_client.put(RUTA_MP, json={
        "mp_access_token": "APP_USR-x", "mp_user_id": "1", "mp_pos_id": "CAJA01",
        "mp_auto_facturar_ventas": False,
    })
    assert mp_qr.esta_configurado() is True


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


# ── La orden en la caja ──────────────────────────────────────────────────


def test_poner_el_monto_manda_el_total_las_lineas_y_las_tres_credenciales(admin_client, mp):
    _configurar_mp(admin_client)
    sale_id, _ = _borrador_con_item(admin_client, cantidad="2", price="1500.00")

    respuesta = admin_client.post(f"/sales/{sale_id}/mp-qr")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["amount"] == 3000.0

    assert len(mp.ordenes) == 1
    orden = mp.ordenes[0]
    assert orden["user_id"] == "123456789"
    assert orden["pos_id"] == "CAJA01"
    assert orden["access_token"] == "APP_USR-token-de-prueba"
    assert orden["total"] == 3000.0
    assert orden["external_reference"] == respuesta.json()["external_reference"]
    # Las líneas van con el precio FINAL, que es lo que el cliente ve al
    # escanear. El desglose de IVA es de la factura, no del cobro.
    assert orden["items"] == [{
        "producto_id": orden["items"][0]["producto_id"],
        "nombre": "Fideos 500g",
        "qty": 2.0,
        "precio": 1500.0,
        "subtotal": 3000.0,
    }]


def test_cada_intento_usa_una_referencia_distinta(admin_client, mp):
    """Reusarla haría que un pago rechazado que MercadoPago acredita tarde
    vuelva como aprobado para el intento siguiente — que puede ser por otra
    plata, si entre medio se agregó una línea."""
    _configurar_mp(admin_client)
    sale_id, _ = _borrador_con_item(admin_client)

    primera = admin_client.post(f"/sales/{sale_id}/mp-qr").json()["external_reference"]
    segunda = admin_client.post(f"/sales/{sale_id}/mp-qr").json()["external_reference"]
    assert primera != segunda
    assert primera.startswith(f"vl-{sale_id}-")
    assert segunda.startswith(f"vl-{sale_id}-")


def test_un_borrador_vacio_no_se_puede_poner_en_el_qr(admin_client, mp):
    _configurar_mp(admin_client)
    _abrir_turno(admin_client)
    sale_id = admin_client.post("/sales", json={}).json()["id"]

    respuesta = admin_client.post(f"/sales/{sale_id}/mp-qr")
    assert respuesta.status_code == 502, respuesta.text
    assert mp.ordenes == []


def test_si_mercadopago_rechaza_la_orden_no_queda_una_fila_diciendo_que_si(admin_client, mp, monkeypatch):
    """El 404 de un POS ID inexistente tiene que llegar al operador, y no
    dejar una orden `pending` contra la que después se polleé para siempre."""
    _configurar_mp(admin_client)
    sale_id, _ = _borrador_con_item(admin_client)

    async def explota(**kwargs):
        raise RuntimeError("MP QR error 404: {'message': 'pos not found'}")

    monkeypatch.setattr(mp_api, "crear_orden_qr", explota)
    respuesta = admin_client.post(f"/sales/{sale_id}/mp-qr")
    assert respuesta.status_code == 502, respuesta.text
    assert "404" in respuesta.json()["detail"]

    # Sin orden guardada, el poll dice `sin_orden` en vez de quedarse
    # esperando un pago que nunca se pidió.
    estado = admin_client.get(f"/sales/{sale_id}/mp-status")
    assert estado.json()["status"] == "sin_orden"


def test_bajar_del_qr_saca_la_orden_de_la_caja(admin_client, mp):
    """Una orden que queda puesta le cobra ese monto al próximo que escanee."""
    _configurar_mp(admin_client)
    sale_id, _ = _borrador_con_item(admin_client)
    admin_client.post(f"/sales/{sale_id}/mp-qr")

    bajada = admin_client.delete(f"/sales/{sale_id}/mp-qr")
    assert bajada.status_code == 204, bajada.text
    assert mp.bajas == [("123456789", "CAJA01")]

    # Idempotente: bajarla de nuevo no vuelve a pegarle a MercadoPago.
    admin_client.delete(f"/sales/{sale_id}/mp-qr")
    assert len(mp.bajas) == 1


# ── El poll ──────────────────────────────────────────────────────────────


def test_mientras_nadie_escanee_el_poll_dice_pendiente(admin_client, mp):
    _configurar_mp(admin_client)
    sale_id, _ = _borrador_con_item(admin_client)
    admin_client.post(f"/sales/{sale_id}/mp-qr")

    estado = admin_client.get(f"/sales/{sale_id}/mp-status")
    assert estado.status_code == 200, estado.text
    assert estado.json() == {"status": "pending", "payment_id": None}


def test_un_pago_rechazado_no_acredita_nada(admin_client, mp):
    _configurar_mp(admin_client)
    sale_id, _ = _borrador_con_item(admin_client)
    admin_client.post(f"/sales/{sale_id}/mp-qr")
    mp.pago = {"id": 999, "status": "rejected"}

    estado = admin_client.get(f"/sales/{sale_id}/mp-status")
    assert estado.json() == {"status": "rejected", "payment_id": None}


def test_el_poll_sella_el_payment_id_y_deja_de_preguntarle_a_mercadopago(admin_client, mp):
    _configurar_mp(admin_client)
    sale_id, _ = _borrador_con_item(admin_client)
    admin_client.post(f"/sales/{sale_id}/mp-qr")
    mp.pago = {"id": 112233, "status": "approved"}

    primera = admin_client.get(f"/sales/{sale_id}/mp-status")
    assert primera.json() == {"status": "approved", "payment_id": "112233"}
    assert len(mp.busquedas) == 1

    # El POS pollea cada 3 segundos: el segundo tick tiene que salir de la
    # fila ya sellada y no de otra consulta a MercadoPago.
    segunda = admin_client.get(f"/sales/{sale_id}/mp-status")
    assert segunda.json() == {"status": "approved", "payment_id": "112233"}
    assert len(mp.busquedas) == 1


def test_con_el_pago_acreditado_no_se_puede_rotar_la_referencia(admin_client, mp):
    """Volver a poner el monto dejaría el pago ya cobrado sin nada que lo ate
    a la venta: la referencia nueva no lo encuentra y la vieja ya no se
    consulta."""
    _configurar_mp(admin_client)
    sale_id, _ = _borrador_con_item(admin_client)
    admin_client.post(f"/sales/{sale_id}/mp-qr")
    mp.pago = {"id": 112233, "status": "approved"}
    admin_client.get(f"/sales/{sale_id}/mp-status")

    respuesta = admin_client.post(f"/sales/{sale_id}/mp-qr")
    assert respuesta.status_code == 409, respuesta.text
    assert len(mp.ordenes) == 1


# ── El confirm: la referencia y la factura ───────────────────────────────


def _confirmar_por_qr(client, sale_id, location_id, total="3000.00", **extra):
    return client.post(f"/sales/{sale_id}/confirm", json={
        "location_id": location_id,
        "pagos": [{"medio": "mercadopago", "monto": total}],
        **extra,
    })


def _cobrar_el_qr(client, mp, sale_id, payment_id=112233):
    client.post(f"/sales/{sale_id}/mp-qr")
    mp.pago = {"id": payment_id, "status": "approved"}
    estado = client.get(f"/sales/{sale_id}/mp-status")
    assert estado.json()["status"] == "approved", estado.text


def test_confirmar_despues_del_qr_sella_el_payment_id_en_la_linea_de_pago(admin_client, mp):
    _configurar_mp(admin_client)
    sale_id, location_id = _borrador_con_item(admin_client)
    _cobrar_el_qr(admin_client, mp, sale_id)

    confirmada = _confirmar_por_qr(admin_client, sale_id, location_id)
    assert confirmada.status_code == 200, confirmada.text
    pagos = confirmada.json()["pagos"]
    assert len(pagos) == 1
    assert pagos[0]["referencia"] == "mp-112233"


def test_una_referencia_que_manda_el_pos_no_se_pisa(admin_client, mp):
    """La referencia es un campo libre —el lote de la tarjeta, el comprobante
    de la transferencia—; pisarla perdería ese dato."""
    _configurar_mp(admin_client)
    sale_id, location_id = _borrador_con_item(admin_client)
    _cobrar_el_qr(admin_client, mp, sale_id)

    confirmada = admin_client.post(f"/sales/{sale_id}/confirm", json={
        "location_id": location_id,
        "pagos": [{"medio": "mercadopago", "monto": "3000.00", "referencia": "lote-77"}],
    })
    assert confirmada.json()["pagos"][0]["referencia"] == "lote-77"


def test_una_venta_en_efectivo_no_se_lleva_la_referencia_del_qr(admin_client, mp):
    """Control negativo del sellado: el `payment_id` va sobre la línea que se
    cobró por QR, no sobre cualquiera."""
    _configurar_mp(admin_client)
    sale_id, location_id = _borrador_con_item(admin_client)
    _cobrar_el_qr(admin_client, mp, sale_id)

    confirmada = admin_client.post(f"/sales/{sale_id}/confirm", json={
        "location_id": location_id,
        "pagos": [{"medio": "efectivo", "monto": "3000.00", "recibido": "3000.00"}],
    })
    assert confirmada.json()["pagos"][0]["referencia"] == ""


def test_con_la_automatica_prendida_la_venta_sale_facturada_sin_pedirlo(admin_client, mp):
    """El POS no manda `invoice`: la decisión es del backend.

    Si la resolviera la pantalla, cualquier otro cliente de la API cobraría por
    QR sin facturar y nada avisaría.
    """
    _configurar_mp(admin_client, auto_facturar=True)
    sale_id, location_id = _borrador_con_item(admin_client)
    _cobrar_el_qr(admin_client, mp, sale_id)

    confirmada = _confirmar_por_qr(admin_client, sale_id, location_id)
    assert confirmada.status_code == 200, confirmada.text
    factura = confirmada.json()["factura"]
    assert factura is not None
    assert float(factura["total"]) == 3000.0


def test_sin_la_automatica_el_mismo_cobro_no_factura(admin_client, mp):
    """El control negativo del test de arriba: con la automática apagada, el
    mismo camino tiene que dejar la venta sin comprobante. Sin esto, un
    `facturar = True` incondicional pasaría los dos."""
    _configurar_mp(admin_client, auto_facturar=False)
    sale_id, location_id = _borrador_con_item(admin_client)
    _cobrar_el_qr(admin_client, mp, sale_id)

    confirmada = _confirmar_por_qr(admin_client, sale_id, location_id)
    assert confirmada.status_code == 200, confirmada.text
    assert confirmada.json()["factura"] is None


def test_la_automatica_no_factura_una_venta_que_no_se_cobro_por_qr(admin_client, mp):
    """La automática es del cobro con QR, no un "facturar todo": una venta en
    efectivo con el toggle prendido sigue sin comprobante."""
    _configurar_mp(admin_client, auto_facturar=True)
    sale_id, location_id = _borrador_con_item(admin_client)

    confirmada = admin_client.post(f"/sales/{sale_id}/confirm", json={
        "location_id": location_id,
        "pagos": [{"medio": "efectivo", "monto": "3000.00", "recibido": "3000.00"}],
    })
    assert confirmada.status_code == 200, confirmada.text
    assert confirmada.json()["factura"] is None


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

    sale_id, location_id = _borrador_con_item(admin_client)
    _cobrar_el_qr(admin_client, mp, sale_id)

    confirmada = _confirmar_por_qr(admin_client, sale_id, location_id)
    assert confirmada.status_code == 200, confirmada.text
    assert confirmada.json()["factura"] is None

    # Y el POS se entera de que no va a facturar, en vez de prometerlo.
    assert admin_client.get("/sales/mp/estado").json() == {
        "disponible": True, "auto_facturar": False,
    }


# ── La configuración ─────────────────────────────────────────────────────


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
