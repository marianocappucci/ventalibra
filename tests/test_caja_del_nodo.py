"""La caja del nodo sube al central (libracore ADR-076, libracommerce ADR-069, ADR-091 de este producto; decisión del humano,
2026-10-21).

Un nodo de LibraEdge abre y cierra turnos y cierra el día sin ver al central. Lo que cablea este producto es
`offline.GANCHOS_DE_CAJA` en el router de turnos y en el del cierre diario; el mecanismo (el payload, los aplicadores del
central, la idempotencia) es de los motores y lo prueban ellos. Acá se mide el cableado por el **flujo HTTP real**: un
gancho que no llega a la ruta no se ve llamando a la función del motor. La subida al central, con dos bases, está en
`test_libraedge_de_punta_a_punta.py`.

VentaLibra no monta `build_caja_router` (no hay ingresos ni egresos a mano) y no abre turnos con `libracore.db.turnos`
directo: el turno se abre y se cierra por `build_turnos_router`. Por eso no hay un `caja.movimiento` que probar acá, salvo
que **no** aparezca: la caja de una venta sube con la venta.

También la guarda de reabrir un día (el nodo no la tiene) y la bandeja de comprobantes pendientes del nodo (libra-ui ADR-087).
"""
import pytest
from libracommerce.erp import offline_caja
from ventas_helpers import abrir_turno, caja_default, crear_item, registrar_venta, sucursal_default

NODO = "nodo-caja-1"
PREFIJO = "S02"


@pytest.fixture()
def como_nodo(monkeypatch, tmp_path):
    """Esta instancia se comporta como un nodo offline registrado (con el prefijo que le dio el central), sin conexión:
    no hay archivo de estado."""
    monkeypatch.delenv("VENTALIBRA_EDGE_NODE_ID", raising=False)
    monkeypatch.setenv("LIBRAEDGE_NODE_ID", NODO)
    monkeypatch.setenv("LIBRAEDGE_PREFIJO", PREFIJO)
    monkeypatch.setenv("LIBRAEDGE_ESTADO", str(tmp_path / "estado.json"))
    return NODO


def _fuera_de_un_nodo(monkeypatch):
    monkeypatch.delenv("LIBRAEDGE_NODE_ID", raising=False)
    monkeypatch.delenv("VENTALIBRA_EDGE_NODE_ID", raising=False)


def _outbox():
    from libracore.db.core import get_connection
    from libraedge.db.repository import NodeRepository

    with get_connection() as conn:
        return NodeRepository(conn).list_pending_operations()


def _tipos():
    return [op.operation_type for op in _outbox()]


def _cerrar_turno(client, turno_id, declarado):
    r = client.post(f"/api/turnos/{turno_id}/cerrar", json={"monto_declarado": declarado, "notas": ""})
    assert r.status_code == 200, r.text
    return r.json()


def _cerrar_dia(client):
    r = client.post("/api/cierre-diario/cerrar", json={"sucursal_id": sucursal_default(client)["id"], "notas": ""})
    assert r.status_code == 200, r.text
    return r.json()


# ── Fuera de un nodo no cambia nada ─────────────────────────────────────────────────────────────────────────────────


def test_fuera_de_un_nodo_la_caja_no_encola_nada(admin_client, monkeypatch):
    """🔴 El camino de siempre no puede cambiar: la inmensa mayoría de las instancias no son nodos."""
    _fuera_de_un_nodo(monkeypatch)
    producto = crear_item(admin_client)

    turno_id = abrir_turno(admin_client)
    registrar_venta(admin_client, producto, precio="1500.00", cantidad="2")
    cerrado = _cerrar_turno(admin_client, turno_id, 3000.0)
    cierre = _cerrar_dia(admin_client)

    assert cerrado["estado"] == "cerrado" and float(cerrado["monto_esperado_cierre"]) == 3000.0
    assert cierre["numero"] == 1
    assert _outbox() == ()


# ── En un nodo todo sube, en el orden en que pasó ───────────────────────────────────────────────────────────────────


def test_en_un_nodo_abrir_vender_cerrar_el_turno_y_cerrar_el_dia_encolan_en_orden(admin_client, como_nodo):
    producto = crear_item(admin_client)
    caja = caja_default(admin_client)
    turno_id = abrir_turno(admin_client, monto_inicial=1000, caja_id=caja)
    registrar_venta(admin_client, producto, precio="1500.00", cantidad="2")
    _cerrar_turno(admin_client, turno_id, 4000.0)
    cierre = _cerrar_dia(admin_client)

    operaciones = _outbox()
    assert [op.operation_type for op in operaciones] == [
        offline_caja.TIPO_TURNO_ABIERTO, "venta.registrada", offline_caja.TIPO_TURNO_CERRADO,
        offline_caja.TIPO_DIA_CERRADO,
    ]
    assert {op.node_id for op in operaciones} == {NODO}
    secuencias = [op.sequence for op in operaciones]
    assert secuencias == sorted(secuencias) and len(set(secuencias)) == 4, "una sola secuencia por nodo, en orden"
    assert operaciones[0].aggregate_id == operaciones[2].aggregate_id == f"{NODO}:turno:{turno_id}"
    assert operaciones[3].aggregate_id == f"{NODO}:cierre_diario:{cierre['id']}"

    abierto, venta, cerrado, dia = (op.payload for op in operaciones)
    assert abierto["turno_id"] == turno_id and abierto["caja_id"] == caja
    assert float(abierto["monto_inicial"]) == 1000.0
    # El esperado es el del arqueo del nodo: 1000 de apertura + 3000 de la venta en efectivo; el declarado, 4000.
    assert (float(cerrado["monto_esperado"]), float(cerrado["monto_declarado"])) == (4000.0, 4000.0)
    assert dia["cierre_id"] == cierre["id"] and [t["turno_id"] for t in dia["turnos"]] == [turno_id]
    # 🔑 La venta lleva el turno y avisa que escribió el turno en su caja (`Outbox(caja_con_turno=True)`): el central
    # reproduce los movimientos igual para que su arqueo dé lo mismo.
    assert venta["turno_id_nodo"] == turno_id and venta["caja_con_turno"] is True


def test_la_caja_de_una_venta_no_sube_como_movimiento_ni_duplicada(admin_client, como_nodo):
    """Los movimientos que nacen de una venta los reproduce el central al aplicar la venta, la anulación o la
    devolución (los llaman sin `ganchos=`): si además subieran como `caja.movimiento`, quedarían dos veces."""
    producto = crear_item(admin_client)
    abrir_turno(admin_client)
    vendida = registrar_venta(admin_client, producto, precio="1500.00", cantidad="2")
    anulada = registrar_venta(admin_client, producto, precio="1500.00", cantidad="1")
    r = admin_client.post(f"/api/ventas/{anulada['id']}/anular")
    assert r.status_code == 200, r.text

    assert vendida["id"] != anulada["id"]
    tipos = _tipos()
    assert tipos == [offline_caja.TIPO_TURNO_ABIERTO, "venta.registrada", "venta.registrada", "venta.anulada"]
    assert offline_caja.TIPO_MOVIMIENTO not in tipos and offline_caja.TIPO_MOVIMIENTO_ANULADO not in tipos


def test_si_el_encolado_falla_el_turno_sigue_abierto(admin_client, como_nodo, monkeypatch):
    """El gancho corre adentro de la transacción del cierre: un turno que se cierra en el nodo y no sube no es un
    cierre a medias, es una caja que el central no ve. Se revierte entero."""
    turno_id = abrir_turno(admin_client)

    def roto(*args, **kwargs):
        raise RuntimeError("outbox roto")

    monkeypatch.setattr(offline_caja, "_encolar", roto)
    with pytest.raises(RuntimeError, match="outbox roto"):
        admin_client.post(f"/api/turnos/{turno_id}/cerrar", json={"monto_declarado": 0, "notas": ""})
    monkeypatch.undo()

    assert admin_client.get(f"/api/turnos/{turno_id}").json()["turno"]["estado"] == "abierto"
    assert _tipos() == [offline_caja.TIPO_TURNO_ABIERTO]


# ── Reabrir un día no tiene gancho: en un nodo se hace en el central ────────────────────────────────────────────────


def test_reabrir_un_dia_en_un_nodo_es_solo_en_el_central(admin_client, monkeypatch):
    """Un nodo que reabriera el día dejaría al central con el día cerrado. Es 409 `solo_en_el_central` en el nodo y
    anda como siempre fuera de él."""
    _fuera_de_un_nodo(monkeypatch)
    turno_id = abrir_turno(admin_client)
    _cerrar_turno(admin_client, turno_id, 0.0)
    cierre = _cerrar_dia(admin_client)
    ruta = f"/api/cierre-diario/{cierre['id']}/reabrir"

    monkeypatch.setenv("LIBRAEDGE_NODE_ID", NODO)
    r = admin_client.post(ruta, json={"motivo": "me equivoqué en el arqueo"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "solo_en_el_central", r.text
    assert _tipos() == [], "no se encoló nada: el día sigue cerrado"

    _fuera_de_un_nodo(monkeypatch)
    r = admin_client.post(ruta, json={"motivo": "me equivoqué en el arqueo"})
    assert r.status_code == 200, r.text


def test_reabrir_un_dia_sigue_siendo_de_admin_en_un_nodo(encargado_client, como_nodo):
    """El rol se chequea antes que el nodo: quien no puede reabrir recibe 403, no el 409 del nodo."""
    r = encargado_client.post("/api/cierre-diario/999999/reabrir", json={"motivo": "x"})
    assert r.status_code == 403, r.text


# ── La bandeja de comprobantes pendientes del nodo (libra-ui ADR-087) ───────────────────────────────────────────────


def _venta_sin_conexion(client):
    """Una venta de mostrador cobrada en el nodo sin conexión a la que se le pidió la factura: queda en la bandeja."""
    from libracore.db import arca_config as db_arca

    producto = crear_item(client)
    db_arca.crear_arca_config("Comercio Ficticio", "20000000001", 3, "", "", ambiente="homologacion")
    abrir_turno(client)
    venta = registrar_venta(client, producto, precio="1500.00", cantidad="2")
    r = client.post(f"/api/ventas/{venta['id']}/facturar")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "factura_pendiente", r.text
    return venta


def test_la_bandeja_del_nodo_trae_la_venta_cobrada_sin_conexion(admin_client, como_nodo):
    venta = _venta_sin_conexion(admin_client)

    r = admin_client.get("/api/comprobantes-pendientes")
    assert r.status_code == 200, r.text
    pendientes = r.json()["pendientes"]
    assert [(c["origen_tipo"], c["origen_producto"], c["origen_id"]) for c in pendientes] == [
        ("venta", "ventalibra", str(venta["id"]))]
    assert admin_client.get("/api/nodo/conexion").json()["a_facturar"] == 1


def test_las_ventas_del_nodo_no_se_descartan_ni_se_facturan_con_el_formulario(admin_client, como_nodo):
    _venta_sin_conexion(admin_client)
    comprobante = admin_client.get("/api/comprobantes-pendientes").json()["pendientes"][0]

    r = admin_client.post(f"/api/comprobantes-pendientes/{comprobante['id']}/descartar", json={"motivo": "x"})
    assert r.status_code == 409, r.text
    r = admin_client.post("/api/comprobantes-pendientes/facturar-prefill", json={"ids": [comprobante["id"]]})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "se_factura_desde_la_venta", r.text


def test_el_mostrador_no_ve_la_bandeja_de_las_ventas_ajenas(cajero_client, como_nodo):
    """La bandeja lista las ventas de todos los turnos (`ventas.todas`): el cajero sólo ve las suyas (ADR-068)."""
    assert cajero_client.get("/api/comprobantes-pendientes").status_code == 403
    assert cajero_client.get("/api/nodo/conexion").status_code == 200, "el cartel «sin conexión» sí es del mostrador"


def test_fuera_de_un_nodo_la_bandeja_esta_vacia(admin_client, monkeypatch):
    """Este producto no monta la ingesta de otros sistemas: fuera de un nodo no llega nada."""
    _fuera_de_un_nodo(monkeypatch)
    r = admin_client.get("/api/comprobantes-pendientes")
    assert r.status_code == 200
    assert r.json() == {"pendientes": [], "facturados": [], "descartados": [], "total_pendientes": 0}
    assert admin_client.get("/api/nodo/conexion").json()["es_nodo"] is False
