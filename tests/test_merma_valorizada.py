"""Importes de merma y conciliación del «sin lote» en VentaLibra (ADR-086; libracommerce v0.60.0, ADR-059 y ADR-060 del motor).

La cuenta (el costo que se guarda al mermar, el reporte, el reparto FEFO) la prueba el motor. Acá, lo que es de este producto:

- el humano decidió (2026-10-14) que **los importes de merma los vean sólo el encargado y el admin** (`costos.ver`): el depósito da de baja un
  lote pero recibe la respuesta sin plata, y el historial de stock y el reporte de mermas siguen la misma regla;
- que el historial de stock valoriza la merma (`OpcionesStock.con_costo_de_merma`; VentaLibra no ofrece el modo «Merma» del ajuste: se merma
  dando de baja un lote);
- que conciliar el «sin lote» negativo es de quien mueve lotes (`vencimientos.mover`: encargado y depósito), vista previa incluida.
"""
import pytest
from test_vencimientos import _merma, escenario  # noqa: F401  (`escenario` es un fixture)

#: El costo que deja la recepción del escenario como `default_cost` de la Leche.
COSTO = 543.21
_CLAVES_DE_COSTO = {"costo_unitario", "costo_total", "sin_costo"}


@pytest.mark.parametrize("rol", ["admin", "encargado"])
def test_quien_ve_costos_recibe_el_importe_de_la_baja_de_un_lote(escenario, rol):  # noqa: F811
    r = _merma(escenario["clientes"][rol], escenario, f"merma-{rol}")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["costo_unitario"] == COSTO
    assert cuerpo["costo_total"] == round(4 * COSTO, 2)
    assert cuerpo["sin_costo"] is False


def test_el_deposito_da_de_baja_un_lote_pero_sin_plata(escenario):  # noqa: F811
    r = _merma(escenario["clientes"]["deposito"], escenario, "merma-deposito")
    assert r.status_code == 200, r.text
    assert r.json()["cantidad"] == 4
    assert not _CLAVES_DE_COSTO & r.json().keys()


def _movimiento_de_merma(cliente, producto):
    r = cliente.get("/api/stock/movimientos", params={"producto_id": producto})
    assert r.status_code == 200, r.text
    return next(m for m in r.json() if m["tipo"] == "merma")


def test_el_historial_de_stock_valoriza_la_merma_solo_para_quien_ve_costos(escenario):  # noqa: F811
    """`OpcionesStock.con_costo_de_merma`: la fila de la merma trae su importe; el depósito, que la ve, la recibe sin plata."""
    c = escenario["clientes"]
    assert _merma(c["deposito"], escenario, "merma-historial").status_code == 200

    visto = _movimiento_de_merma(c["encargado"], escenario["leche"])
    assert (visto["costo_unitario"], visto["costo_total"], visto["sin_costo"]) == (COSTO, round(4 * COSTO, 2), False)
    assert not _CLAVES_DE_COSTO & _movimiento_de_merma(c["deposito"], escenario["leche"]).keys()


@pytest.mark.parametrize("rol", ["admin", "encargado"])
def test_el_reporte_de_mermas_es_de_quien_ve_costos(escenario, rol):  # noqa: F811
    assert _merma(escenario["clientes"]["encargado"], escenario, "merma-reporte").status_code == 200
    r = escenario["clientes"][rol].get("/api/reportes/mermas")
    assert r.status_code == 200, r.text
    assert r.json()["resumen"]["costo_total"] == round(4 * COSTO, 2)
    assert escenario["clientes"][rol].get("/api/reportes/mermas/export").status_code == 200


@pytest.mark.parametrize("rol", ["deposito", "vendedor", "cajero"])
def test_el_reporte_de_mermas_no_es_del_deposito_ni_del_mostrador(escenario, rol):  # noqa: F811
    cliente = escenario["clientes"][rol]
    assert cliente.get("/api/reportes/mermas").status_code == 403
    assert cliente.get("/api/reportes/mermas/export").status_code == 403


def _sin_lote_negativo(esc):
    """Lleva el «sin lote» de la Leche a -2 como lo dejaba una venta de antes de A-4: una salida directa del bucket sin lote."""
    conn = esc["clientes"]["admin"].app.state.conn
    conn.execute(
        "INSERT INTO stock_movements (item_id, location_id, movement_type, quantity_delta, occurred_at, note, reason_code) "
        "VALUES (?, ?, 'sale', -10, CURRENT_TIMESTAMP, 'venta vieja', 'venta')",
        (esc["leche"], esc["deposito"]),
    )
    conn.commit()


def _consulta(esc):
    return {"producto_id": esc["leche"], "deposito_id": esc["deposito"]}


@pytest.mark.parametrize("rol", ["admin", "encargado", "deposito"])
def test_quien_mueve_lotes_concilia_el_sin_lote_negativo(escenario, rol):  # noqa: F811
    _sin_lote_negativo(escenario)
    cliente = escenario["clientes"][rol]
    previa = cliente.get("/api/vencimientos/conciliacion", params=_consulta(escenario))
    assert previa.status_code == 200, previa.text
    assert previa.json()["a_conciliar"] == 2

    r = cliente.post("/api/vencimientos/conciliar", json={
        **_consulta(escenario), "reparto": previa.json()["propuesta"], "clave_operacion": f"conc-{rol}"})
    assert r.status_code == 200, r.text
    assert r.json()["saldo_sin_lote"] == 0
    # Con el negativo conciliado, la baja de un lote ya no da el 409 de «salidas sin lote sin conciliar».
    # (FEFO tomó 2 del lote vencido: quedan 2.)
    assert _merma(cliente, escenario, f"merma-despues-{rol}", cantidad=1).status_code == 200


@pytest.mark.parametrize("rol", ["vendedor", "cajero"])
def test_el_mostrador_no_concilia(escenario, rol):  # noqa: F811
    _sin_lote_negativo(escenario)
    cliente = escenario["clientes"][rol]
    assert cliente.get("/api/vencimientos/conciliacion", params=_consulta(escenario)).status_code == 403
    assert cliente.post("/api/vencimientos/conciliar", json={
        **_consulta(escenario), "reparto": [], "clave_operacion": "x"}).status_code == 403
