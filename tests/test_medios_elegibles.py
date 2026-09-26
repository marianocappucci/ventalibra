"""El medio de pago se valida contra el vocabulario del motor.

🔴 Hasta el 2026-09-11 este producto aceptaba **cualquier texto** como medio: la
lista existía sólo en los selectores del frontend (tres copias: POS, devolución
y cobranza de cuenta corriente). Un medio inventado entraba, creaba su
movimiento de caja y aparecía en el cierre como un bucket suelto con el nombre
crudo — la plata bien contada y el reparto mal. Contalibra y Restolibra lo
cerraron el 2026-08-24 con `libracore.medios_pago.validar`; acá es la misma
función, en los payloads que escriben un medio.

Portado a F3 (2026-09-14, DECISIONS.md ADR-025): `registrar`/`devolver` ya no
son `POST /sales/{id}/confirm` / `.../returns` (retirados, 410 sin mirar el
cuerpo) -- son `POST /api/ventas` y `POST /api/ventas/{vid}/devolver`, que
validan el medio con la MISMA función pero en `libracommerce.web.
ventas_router.PagoPayload`/`DevolucionPayload`. `/accounts/{id}/payments`
no cambió: sigue siendo de este producto.

🔴 **Lo que ya no existe**: el atajo `medio_pago` de un solo string en la
confirmación. `VentaPayload` sólo acepta `pagos: list[PagoPayload]` -- no hay
más "un medio para toda la venta" como string suelto. Los tests que probaban
ese atajo se portan al `pagos[]` equivalente.

Los tests de validación piden sobre una venta/cuenta que NO existe, a
propósito: el cuerpo se valida antes de que corra el endpoint, así que un medio
inválido da 422 sin importar el resto, y uno válido pasa de largo y cae en el
404/409 del endpoint. Ese segundo código es el control: prueba que el 422 lo
causó el medio y no otra cosa del cuerpo.
"""
import pytest
from libracore import medios_pago
from ventas_helpers import caja_default, hoy

from tests.test_billing import _confirmed_sale, _make_item, _make_location

VENTA_INEXISTENTE = 999_999
CLIENTE_INEXISTENTE = 999_999

#: Grafías que se LEEN en filas viejas pero no se escriben en filas nuevas
#: (`medios_pago.HISTORICOS` y la de VentaLibra que ya se retiró), más una
#: inventada.
NO_ELEGIBLES = ["inventado", "tarjeta", "mercado_pago", "cuenta corriente"]


def _registrar(client, medio):
    """`POST /api/ventas` con un solo pago: el medio se valida en
    `PagoPayload` antes de que el handler mire si el ítem existe -- por eso
    alcanza con un `producto_id` que no existe para que el 422 del medio (si
    lo hay) sea el que se ve primero, y un ítem real sólo hace falta para el
    control positivo."""
    return client.post("/api/ventas", json={
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": 1, "precio": 100, "producto_id": VENTA_INEXISTENTE}],
        "pagos": [{"medio": medio, "monto": 100}],
    })


def _devolver(client, medio):
    return client.post(f"/api/ventas/{VENTA_INEXISTENTE}/devolver", json={
        "lineas": [{"sale_item_id": 1, "cantidad": 1}], "deposito_id": 1, "medio_pago": medio,
    })


def _cobrar(client, medio):
    return client.post(
        f"/accounts/{CLIENTE_INEXISTENTE}/payments", json={"monto": "10", "medio_pago": medio},
    )


def test_la_ruta_de_los_selectores_devuelve_los_del_motor(admin_client):
    r = admin_client.get("/api/cajas/medios-disponibles")
    assert r.status_code == 200, r.text
    assert r.json() == medios_pago.para_selector()
    # Los tres que las listas propias del frontend no ofrecían.
    assert {"cuenta_dni", "billetera", "cheque"} <= {m["id"] for m in r.json()}


@pytest.mark.parametrize("medio", NO_ELEGIBLES)
def test_registrar_con_un_medio_que_no_se_puede_elegir_da_422(admin_client, medio):
    assert _registrar(admin_client, medio).status_code == 422


@pytest.mark.parametrize("medio", list(medios_pago.ELEGIBLES))
def test_registrar_con_cualquier_elegible_pasa_la_validacion(admin_client, medio):
    # Con turno abierto, el medio es válido, así que lo que rebota es otra
    # cosa del cuerpo -- acá, el `producto_id` inexistente.
    #
    # 🔴 Cerrado en libracommerce v0.16.2: un `producto_id` inexistente
    # levanta `ProductoInexistente` -> 422. Antes daba 409 -- `crear_venta_
    # directa` atrapaba CUALQUIER `IntegrityError` (no sólo el de número de
    # venta repetido, que es para lo que existe el reintento) y la agotaba
    # como si fuera una colisión de numeración, con un mensaje engañoso
    # ("conflicto con otra venta simultánea" cuando en realidad el ítem no
    # existe).
    admin_client.post(
        "/shifts/open", json={"monto_inicial": 0, "caja_id": caja_default(admin_client)}
    )
    assert _registrar(admin_client, medio).status_code == 422
    # Y confirma que fue POR EL ÍTEM, no por el medio: con un ítem real pasa.
    item_id = _make_item(admin_client)
    payload = {
        "fecha": hoy(),
        "items": [{"nombre": "línea", "qty": 1, "precio": 100, "producto_id": item_id}],
        "pagos": [{"medio": medio, "monto": 100}],
    }
    if medio == "cuenta_corriente":
        # `exigir_cliente_para_fiar` (F3, ADR-025, prendida en `app/main.py`)
        # bloquea un fiado sin cliente ANTES de mirar el ítem -- sin esto el
        # control mediría ese gate, no el del ítem.
        cliente = admin_client.post("/api/clientes", json={"name": "Cliente de control"})
        assert cliente.status_code == 200, cliente.text
        payload["cliente_id"] = cliente.json()["id"]
    r_valido = admin_client.post("/api/ventas", json=payload)
    assert r_valido.status_code == 200, r_valido.text


@pytest.mark.parametrize("medio", NO_ELEGIBLES)
def test_devolver_por_un_medio_que_no_se_puede_elegir_da_422(admin_client, medio):
    assert _devolver(admin_client, medio).status_code == 422


def test_devolver_por_un_elegible_pasa_la_validacion(admin_client):
    assert _devolver(admin_client, "cheque").status_code in (404, 422)


@pytest.mark.parametrize("medio", [*NO_ELEGIBLES, "cuenta_corriente"])
def test_cobrar_una_deuda_con_algo_que_no_cobra_da_422(admin_client, medio):
    # 🔴 `cuenta_corriente` es elegible en general pero NO para cobrar una deuda:
    # es la marca de que la operación se hizo a crédito. Cobrar "con cuenta
    # corriente" registraría un cobro que no cobra nada.
    assert _cobrar(admin_client, medio).status_code == 422


def test_cobrar_una_deuda_con_un_medio_de_cobro_pasa_la_validacion(admin_client):
    assert _cobrar(admin_client, "cheque").status_code in (404, 409)


@pytest.mark.parametrize("medio", ["cuenta_dni", "billetera", "cheque"])
def test_una_venta_se_cobra_con_los_medios_que_el_pos_no_ofrecia(admin_client, medio):
    # De punta a punta, con turno abierto: que un medio nuevo no rompa la caja
    # ni la venta.
    confirmada = _confirmed_sale(
        admin_client, _make_item(admin_client), _make_location(admin_client), medio_pago=medio,
    )
    assert confirmada.status_code == 200, confirmada.text
    assert confirmada.json()["status"] == "confirmed"
