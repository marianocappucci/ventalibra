"""El stock de la sucursal de un nodo lo mueve sólo el nodo, y las compras se cargan en la web (ADR-093).

Decisiones del humano (2026-10-21): el stock de una sucursal con nodo lo mueve el nodo (el central contesta 409 sobre sus
depósitos); las transferencias son dentro de la sucursal; **los proveedores y las órdenes de compra se cargan en la web y
bajan al nodo, y en el nodo sólo se recibe contra esas órdenes** (lote, vencimiento y costo), con la recepción subiendo como
`compra.recibida`; la carga inicial trae al nodo las existencias del central; un depósito sin sucursal impide vincular.

Los motores hacen el trabajo (libracommerce ADR-071, libraedge ADR-023); acá se prueba **el cableado del producto** de
punta a punta, con el escenario de dos bases de `test_libraedge_de_punta_a_punta.py`: el nodo es la app sobre la base del
worker con la identidad de un nodo en el entorno, el central es una copia, y lo que el nodo hace llega por las rutas
`/sync/v1/*` reales. Datos ficticios.
"""
import pytest
import test_libraedge_de_punta_a_punta as punta
from test_libraedge_de_punta_a_punta import CENTRAL, NODO, _cable, _en_el_central, _en_el_nodo
from ventas_helpers import ajustar

from app.services.proveedores import OFFSET_PROVEEDOR

#: Un nodo y su central con dos bases: el fixture de `test_libraedge_de_punta_a_punta.py`, que pytest registra con este nombre.
escenario = punta.escenario


def _deposito(esc) -> int:
    return _en_el_nodo(esc, "SELECT id FROM locations WHERE is_default = 1")[0][0]


def _stock_del_nodo(esc) -> float:
    return float(_en_el_nodo(esc, "SELECT COALESCE(SUM(quantity_delta), 0) FROM stock_movements WHERE item_id = ?",
                             (esc.producto,))[0][0])


def _stock_del_central(esc) -> float:
    return float(_en_el_central(esc, "SELECT COALESCE(SUM(quantity_delta), 0) FROM stock_movements WHERE item_id = ?",
                                (esc.producto,))[0][0])


def _compra_en_la_web(esc, cantidad="10", costo="100") -> tuple[int, int]:
    """Lo que hace el encargado en la versión web: un proveedor y una orden de compra enviada. Devuelve `(proveedor, orden)`."""
    with esc.central():
        r = esc.client.post("/api/proveedores", json={"nombre": "Distribuidora Ficticia SA", "cuit_dni": "30-00000000-1"})
        assert r.status_code in (200, 201), r.text
        proveedor = r.json()["id"]
        r = esc.client.post("/api/purchase-orders", json={"proveedor_id": proveedor})
        assert r.status_code == 200, r.text
        orden = r.json()["id"]
        r = esc.client.post(f"/api/purchase-orders/{orden}/items", json={
            "item_id": esc.producto, "quantity_ordered": cantidad, "unit_cost": costo})
        assert r.status_code == 200, r.text
        assert esc.client.post(f"/api/purchase-orders/{orden}/enviar").status_code == 200
    return proveedor, orden


def _recibir(esc, proveedor, orden, cantidad="6", costo="120", clave="recepcion-1", **extra):
    cuerpo = {
        "proveedor_id": proveedor, "purchase_order_id": orden, "deposito_id": _deposito(esc), "clave_operacion": clave,
        "document_reference": "R-0001-00000001",
        "items": [{"item_id": esc.producto, "quantity": cantidad, "unit_cost": costo, "lot_code": "L1",
                   "expires_at": "2027-03-01T00:00:00"}],
    }
    cuerpo.update(extra)
    return esc.client.post("/api/purchase-receipts/recibir", json=cuerpo)


# ── Lo que el nodo mueve sube ─────────────────────────────────────────────────────────────────────────────────────


def test_el_ajuste_de_stock_del_nodo_sube_como_movimiento_y_la_venta_no_se_duplica(escenario):
    """Un ajuste manual en el nodo sube como `stock.movimiento` y el central lo escribe una vez; la venta sube con su propia
    operación (`venta.registrada` lleva la salida): si además subiera como movimiento, el central descontaría dos veces."""
    esc = escenario
    r = ajustar(esc.client, esc.producto, _deposito(esc), 5, motivo="conteo inicial")
    assert r.status_code == 200, r.text
    esc.vender()
    assert esc.pendientes_en_el_nodo() == ["stock.movimiento", "turno.abierto", "venta.registrada"]

    resultado = esc.subir()
    assert resultado.confirmadas == 3 and esc.en_revision_en_el_nodo() == ()
    assert _stock_del_nodo(esc) == 3.0 and _stock_del_central(esc) == 3.0
    origenes = _en_el_central(esc, "SELECT origen FROM stock_movements WHERE origen IS NOT NULL")
    assert origenes == [(NODO,)], "el movimiento del nodo se escribe una vez, con el nodo como origen"

    # Un segundo ciclo no repite nada.
    assert esc.subir().confirmadas == 0
    assert _stock_del_central(esc) == 3.0


def test_la_recepcion_contra_una_orden_de_la_web_sube_y_el_central_la_aplica(escenario):
    """Las órdenes y el proveedor se cargan en la web y bajan; en el nodo se recibe contra la orden y la recepción sube como
    `compra.recibida` (no también como movimiento): en el central la orden avanza, entra el stock y se actualiza el costo."""
    esc = escenario
    proveedor, orden = _compra_en_la_web(esc, cantidad="10", costo="100")
    assert esc.bajar() > 0
    # Bajó todo lo que la recepción necesita: el proveedor, su party, la orden y sus líneas.
    assert _en_el_nodo(esc, "SELECT nombre FROM proveedores WHERE id = ?", (proveedor,)) == [("Distribuidora Ficticia SA",)]
    assert _en_el_nodo(esc, "SELECT display_name FROM parties WHERE id = ?", (OFFSET_PROVEEDOR + proveedor,)) == [
        ("Distribuidora Ficticia SA",)]
    assert _en_el_nodo(esc, "SELECT status FROM purchase_orders WHERE id = ?", (orden,)) == [("sent",)]
    assert _en_el_nodo(esc, "SELECT quantity_ordered FROM purchase_order_items WHERE purchase_order_id = ?", (orden,)) == [(10,)]
    assert esc.client.get("/api/proveedores").status_code == 200, "el nodo lee los proveedores que espeja"

    r = _recibir(esc, proveedor, orden, cantidad="6", costo="120")
    assert r.status_code == 200, r.text
    assert r.json()["proveedor_id"] == proveedor
    assert _stock_del_nodo(esc) == 6.0
    assert esc.pendientes_en_el_nodo() == ["compra.recibida", "turno.abierto"]
    # El nodo no escribió el party del proveedor: sólo lo verificó.
    assert _en_el_nodo(esc, "SELECT COUNT(*) FROM parties WHERE id = ?", (OFFSET_PROVEEDOR + proveedor,)) == [(1,)]

    resultado = esc.subir()
    assert resultado.confirmadas == 2 and esc.en_revision_en_el_nodo() == ()
    assert _en_el_central(esc, "SELECT status FROM purchase_orders WHERE id = ?", (orden,)) == [("partial",)]
    assert _en_el_central(esc, "SELECT quantity_received FROM purchase_order_items WHERE purchase_order_id = ?",
                          (orden,)) == [(6,)]
    assert _stock_del_central(esc) == 6.0
    assert _en_el_central(esc, "SELECT default_cost FROM catalog_items WHERE id = ?", (esc.producto,)) == [(120,)]
    assert _en_el_central(esc, "SELECT lot_code FROM stock_movements WHERE item_id = ? AND lot_code IS NOT NULL",
                          (esc.producto,)) == [("L1",)], "el lote y el vencimiento viajan con la recepción"

    # Un segundo ciclo no repite nada; lo que el central avanzó en la orden baja al nodo.
    assert esc.subir().confirmadas == 0
    assert _stock_del_central(esc) == 6.0
    esc.bajar()
    assert _en_el_nodo(esc, "SELECT status FROM purchase_orders WHERE id = ?", (orden,)) == [("partial",)]

    # Reintentar el mismo envío (la misma clave) no vuelve a mover el stock.
    assert _recibir(esc, proveedor, orden, cantidad="6", costo="120").json().get("repetida") is True
    assert _stock_del_nodo(esc) == 6.0


# ── Lo que el central no mueve ────────────────────────────────────────────────────────────────────────────────────


def test_el_central_no_mueve_el_stock_de_una_sucursal_con_nodo(escenario):
    """Movimientos a mano, ventas web, anular desde la web una venta del nodo y recibir desde la web: 409
    `deposito_de_sucursal_con_nodo`, sin dejar ni un movimiento a medio escribir."""
    from ventas_helpers import hoy

    esc = escenario
    venta = esc.vender()
    proveedor, orden = _compra_en_la_web(esc)
    esc.subir()
    central_vid = _en_el_central(esc, "SELECT id FROM sales WHERE source_id = ?", (venta["id"],))[0][0]
    antes = _stock_del_central(esc)
    deposito = _deposito(esc)

    def es_409(r):
        assert r.status_code == 409, r.text
        assert r.json()["codigo"] == "deposito_de_sucursal_con_nodo" and r.json()["node_id"] == NODO, r.text
        assert "equipo sin conexión" in r.json()["detail"]

    with esc.central():
        es_409(ajustar(esc.client, esc.producto, deposito, 3, motivo="a mano en la web"))
        es_409(ajustar(esc.client, esc.producto, deposito, -1, motivo="a mano en la web"))
        es_409(esc.client.post(f"/api/ventas/{central_vid}/anular"))
        es_409(_recibir(esc, proveedor, orden, clave="desde-la-web"))
        es_409(esc.client.post("/api/ventas", json={
            "fecha": hoy(), "items": [{"nombre": "línea", "qty": 1, "precio": 1500.0, "producto_id": esc.producto}],
            "pagos": [{"medio": "efectivo", "monto": 1500.0}]}))
    assert _stock_del_central(esc) == antes, "el 409 no deja movimientos a medio escribir"
    assert _en_el_central(esc, "SELECT status_detail FROM sales WHERE id = ?", (central_vid,)) == [("cobrada",)]


# ── Lo que el nodo no carga: proveedores y órdenes ────────────────────────────────────────────────────────────────


def test_el_nodo_no_carga_proveedores_ni_ordenes_pero_los_lee(escenario):
    esc = escenario
    proveedor, orden = _compra_en_la_web(esc)
    esc.bajar()

    def solo_en_el_central(r):
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["codigo"] == "solo_en_el_central", r.text
        assert r.json()["detail"]["mensaje"] == "Las órdenes de compra y los proveedores se cargan en la versión web."

    solo_en_el_central(esc.client.post("/api/proveedores", json={"nombre": "Otro SA"}))
    solo_en_el_central(esc.client.put(f"/api/proveedores/{proveedor}", json={"nombre": "Renombrado"}))
    solo_en_el_central(esc.client.delete(f"/api/proveedores/{proveedor}"))
    solo_en_el_central(esc.client.post("/api/purchase-orders", json={"proveedor_id": proveedor}))
    solo_en_el_central(esc.client.post(f"/api/purchase-orders/{orden}/items", json={
        "item_id": esc.producto, "quantity_ordered": "1", "unit_cost": "1"}))
    solo_en_el_central(esc.client.post(f"/api/purchase-orders/{orden}/enviar"))
    solo_en_el_central(esc.client.post(f"/api/purchase-orders/{orden}/cancelar"))
    # La recepción en tres pasos tampoco: se recibe de una vez, contra la orden.
    solo_en_el_central(esc.client.post("/api/purchase-receipts", json={"proveedor_id": proveedor, "purchase_order_id": orden}))
    solo_en_el_central(esc.client.post("/api/purchase-receipts/1/items", json={
        "item_id": esc.producto, "quantity": "1", "unit_cost": "1"}))
    solo_en_el_central(esc.client.post("/api/purchase-receipts/1/confirm", json={"deposito_id": _deposito(esc)}))
    # Y las órdenes en borrador que arma la reposición.
    r = esc.client.post("/api/reportes/reposicion/ordenes", json={})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "solo_en_el_central", r.text

    # No quedó nada escrito, y se lee todo.
    assert _en_el_nodo(esc, "SELECT COUNT(*) FROM proveedores") == [(1,)]
    assert _en_el_nodo(esc, "SELECT COUNT(*) FROM purchase_orders") == [(1,)]
    assert _en_el_nodo(esc, "SELECT COUNT(*) FROM purchase_receipts") == [(0,)]
    assert [p["id"] for p in esc.client.get("/api/proveedores").json()] == [proveedor]
    assert [o["id"] for o in esc.client.get("/api/purchase-orders").json()] == [orden]
    assert esc.client.get(f"/api/purchase-orders/{orden}").json()["proveedor_id"] == proveedor


def test_en_el_nodo_se_recibe_solo_contra_una_orden(escenario):
    esc = escenario
    proveedor, _ = _compra_en_la_web(esc)
    esc.bajar()
    r = _recibir(esc, proveedor, None, clave="sin-orden")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "recepcion_sin_orden", r.text
    assert _stock_del_nodo(esc) == 0.0 and esc.pendientes_en_el_nodo() == ["turno.abierto"]


def test_un_proveedor_que_no_bajo_es_409_y_el_nodo_no_escribe_parties(escenario):
    """`party_de_proveedor` en un nodo sólo verifica: si el proveedor recién cargado en la web todavía no bajó, 409
    `proveedor_sin_sincronizar` y ninguna fila nueva en `parties` (el espejo la pisaría o chocaría con la del central)."""
    esc = escenario
    proveedor, orden = _compra_en_la_web(esc)          # sin `esc.bajar()`: el nodo todavía no se enteró
    assert _en_el_nodo(esc, "SELECT COUNT(*) FROM parties WHERE id = ?", (OFFSET_PROVEEDOR + proveedor,)) == [(0,)]

    r = _recibir(esc, proveedor, orden)
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "proveedor_sin_sincronizar", r.text
    assert _en_el_nodo(esc, "SELECT COUNT(*) FROM parties WHERE id = ?", (OFFSET_PROVEEDOR + proveedor,)) == [(0,)]
    assert _stock_del_nodo(esc) == 0.0

    # Con la bajada, la misma recepción entra.
    esc.bajar()
    assert _recibir(esc, proveedor, orden).status_code == 200


# ── La carga inicial ──────────────────────────────────────────────────────────────────────────────────────────────


def _carga_inicial(esc, monkeypatch):
    """El worker de LibraEdge del nodo, con la función de LibraCommerce y la ruta `/sync/v1/carga-inicial` real del central."""
    from libraedge.db.repository import NodeRepository
    from libraedge.sync import carga_inicial as modulo
    from libraedge.sync.carga_inicial import CargaInicialWorker, HttpCargaInicialTransport

    monkeypatch.setattr(modulo, "urlopen", _cable(esc))
    return CargaInicialWorker(
        NodeRepository(esc.node_conn), esc.node_conn, NODO,
        HttpCargaInicialTransport(CENTRAL, NODO, esc.secreto, version_esquema=esc._version()),
        "libracommerce.erp.offline_stock:aplicar_carga_inicial")


def test_la_carga_inicial_trae_las_existencias_del_central_y_no_duplica_lo_que_el_nodo_ya_vendio(escenario, monkeypatch):
    """Central con stock -> el nodo vincula -> se ajusta al saldo del central. Una venta del nodo que ya subió está en las dos
    puntas: no se cuenta dos veces. Volver a correrla no escribe nada."""
    from libracommerce.erp import offline_stock
    from libracommerce.erp.stock import add_movimiento_stock
    from libracore.db.core import get_connection

    esc = escenario
    esc.bajar()
    # El stock que ya tenía el central antes de vincular el nodo (sobre un depósito que ahora es del nodo: lo escribe el central
    # «como el nodo», que es lo que la guarda deja pasar).
    with esc.central(), get_connection() as conn, offline_stock.aplicando():
        add_movimiento_stock(conn, esc.producto, "entrada", 10, referencia="conteo", deposito_id=_deposito(esc))
        conn.commit()
    assert _stock_del_central(esc) == 10.0 and _stock_del_nodo(esc) == 0.0

    esc.vender()                       # el nodo vende 2 sin tener existencias cargadas: queda en -2
    esc.subir()                        # el central aplica la venta: 10 - 2 = 8
    assert _stock_del_central(esc) == 8.0 and _stock_del_nodo(esc) == -2.0

    resultado = _carga_inicial(esc, monkeypatch).run_once()
    assert resultado.estado == "hecha", resultado
    assert _stock_del_nodo(esc) == 8.0, "el nodo queda igual que el central, sin sumar dos veces la venta"
    assert _en_el_nodo(esc, "SELECT reason_code FROM stock_movements WHERE reason_code = 'carga_inicial'") == [("carga_inicial",)]
    assert esc.pendientes_en_el_nodo() == [], "la carga inicial viene del central: no sube de vuelta"

    # Ya hecha: otro ciclo no vuelve a traerla.
    assert _carga_inicial(esc, monkeypatch).run_once().estado == "ya_hecha"
    assert _stock_del_nodo(esc) == 8.0
    # Y forzarla (soporte) da delta cero: es idempotente.
    forzada = _carga_inicial(esc, monkeypatch).run_once(forzar=True)
    assert forzada.estado == "hecha" and forzada.resultado["ajustes"] == 0
    assert _stock_del_nodo(esc) == 8.0


def test_la_carga_inicial_es_autenticada_por_el_nodo(escenario):
    esc = escenario
    assert esc.client.get("/sync/v1/carga-inicial", params={"node_id": NODO}).status_code == 401
    r = esc.client.get("/sync/v1/carga-inicial", params={"node_id": NODO}, headers={"Authorization": "Bearer inventado"})
    assert r.status_code == 401


# ── Los depósitos sin sucursal ────────────────────────────────────────────────────────────────────────────────────


def test_registrar_un_nodo_con_un_deposito_sin_sucursal_se_niega(escenario):
    """Un depósito sin sucursal no es de ningún nodo: la guarda del central no lo ve y la carga inicial no lo trae. Hasta que
    tenga sucursal no se vincula nada (ni siquiera la PC de un nodo que se reemplaza)."""
    from libracore.db.core import get_connection
    from libraedge import aprovisionamiento as aprov
    from libraedge.aprovisionamiento import RegistroConProblemas

    from app import offline

    esc = escenario
    with esc.central(), get_connection() as conn:
        sucursal = str(conn.execute("SELECT id FROM branches WHERE is_default = 1").fetchone()[0])
        conn.execute("INSERT INTO locations (name, branch_id, location_type) VALUES ('Depósito suelto', NULL, 'warehouse')")
        conn.commit()
        antes = conn.execute("SELECT COUNT(*) FROM node_identity").fetchone()[0]
        with pytest.raises(RegistroConProblemas) as error:
            aprov.registrar(conn, offline.aprovisionamiento, NODO, sucursal, salida=lambda _linea: None)
        assert "Depósito suelto" in str(error.value)
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM node_identity").fetchone()[0] == antes, "no escribió nada"

        # Con la sucursal asignada, se puede.
        conn.execute("UPDATE locations SET branch_id = ? WHERE name = 'Depósito suelto'", (int(sucursal),))
        conn.commit()
        assert aprov.registrar(conn, offline.aprovisionamiento, NODO, sucursal, salida=lambda _linea: None).secreto
