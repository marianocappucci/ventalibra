"""El medio de pago se valida contra el vocabulario del motor.

🔴 Hasta el 2026-09-11 este producto aceptaba **cualquier texto** como medio: la
lista existía sólo en los selectores del frontend (tres copias: POS, devolución
y cobranza de cuenta corriente). Un medio inventado entraba, creaba su
movimiento de caja y aparecía en el cierre como un bucket suelto con el nombre
crudo — la plata bien contada y el reparto mal. Contalibra y Restolibra lo
cerraron el 2026-08-24 con `libracore.medios_pago.validar`; acá es la misma
función, en los tres payloads que escriben un medio.

Los tests de validación piden sobre ventas y cuentas que NO existen, a
propósito: el cuerpo se valida antes de que corra el endpoint, así que un medio
inválido da 422 sin importar el resto, y uno válido pasa de largo y cae en el
404/409 del endpoint. Ese segundo código es el control: prueba que el 422 lo
causó el medio y no otra cosa del cuerpo.
"""
import pytest
from libracore import medios_pago

from tests.test_billing import _confirmed_sale, _make_item, _make_location

VENTA_INEXISTENTE = 999_999
CLIENTE_INEXISTENTE = 999_999

#: Grafías que se LEEN en filas viejas pero no se escriben en filas nuevas
#: (`medios_pago.HISTORICOS` y la de VentaLibra que ya se retiró), más una
#: inventada.
NO_ELEGIBLES = ["inventado", "tarjeta", "mercado_pago", "cuenta corriente"]


def _confirmar(client, **cuerpo):
    return client.post(f"/sales/{VENTA_INEXISTENTE}/confirm", json={"location_id": 1, **cuerpo})


def _devolver(client, medio):
    return client.post(f"/sales/{VENTA_INEXISTENTE}/returns", json={
        "lineas": [{"index": 0, "quantity": "1"}], "location_id": 1, "medio_pago": medio,
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
def test_confirmar_con_un_medio_que_no_se_puede_elegir_da_422(admin_client, medio):
    assert _confirmar(admin_client, medio_pago=medio).status_code == 422
    assert _confirmar(admin_client, pagos=[{"medio": medio, "monto": "1"}]).status_code == 422


@pytest.mark.parametrize("medio", list(medios_pago.ELEGIBLES))
def test_confirmar_con_cualquier_elegible_pasa_la_validacion(admin_client, medio):
    # Control: el cuerpo es válido, así que contesta el endpoint.
    assert _confirmar(admin_client, medio_pago=medio).status_code in (404, 409)
    assert _confirmar(admin_client, pagos=[{"medio": medio, "monto": "1"}]).status_code in (404, 409)


def test_medio_pago_vacio_no_es_un_medio_invalido(admin_client):
    # Vacío es "no vino": manda `pagos`.
    r = _confirmar(admin_client, medio_pago="", pagos=[{"medio": "efectivo", "monto": "1"}])
    assert r.status_code in (404, 409)


@pytest.mark.parametrize("medio", NO_ELEGIBLES)
def test_devolver_por_un_medio_que_no_se_puede_elegir_da_422(admin_client, medio):
    assert _devolver(admin_client, medio).status_code == 422


def test_devolver_por_un_elegible_pasa_la_validacion(admin_client):
    assert _devolver(admin_client, "cheque").status_code in (404, 409)


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
    # ni la venta, que se confirman fuera de una transacción común.
    confirmada = _confirmed_sale(
        admin_client, _make_item(admin_client), _make_location(admin_client), medio_pago=medio,
    )
    assert confirmada.status_code == 200, confirmada.text
    assert confirmada.json()["status"] == "confirmed"
