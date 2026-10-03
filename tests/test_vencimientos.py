"""Vencimientos y lotes con los routers del motor (`/api/vencimientos`, roadmap de producto A-3, ADR-052).

`libracommerce.web.vencimientos_router` (v0.29.0, ADR-018 del motor): la cuenta (ventana de días, vencido contra por vencer, `sin_lote`
por depósito, la idempotencia por `clave_operacion`, la concurrencia) es del motor y se prueba allá contra los dos motores de base.
Acá se prueba el CABLEADO en VentaLibra: que las tres capacidades nuevas mandan (`vencimientos.ver` y `vencimientos.mover` para el
encargado y el depósito, `vencimientos.marcar` sólo para el encargado, y el admin todas), que el ledger se carga por el camino real de este
producto (una recepción de compra con lote y vencimiento, que hace el encargado), que las escrituras quedan a nombre de quien las hizo,
que la revisión Alembic `0002_vencimientos_lotes` del motor está aplicada en la instancia de pruebas, que no hay gate de plan y que
NINGUNA respuesta lleva costos.

Los números del escenario, a mano (hoy = la fecha de Argentina; la ventana por defecto es de 15 días): la Leche entra por una
recepción con tres lotes (uno vencido hace 3 días con 4 unidades, uno que vence en 5 días con 10 y uno que vence en 60 con 6) y
8 unidades sin lote por un ajuste de entrada. Con la ventana de 15 días el reporte trae el vencido (4) y el que vence en 5 días (10); el
de 60 días entra sólo con `dias=90`; y las 8 sin lote salen en `sin_lote` como `sin_fecha`.

Desde libracommerce v0.30.0 (A-4 completo en el motor, ADR-053) el producto marcado «vence» sigue el lote en TODAS sus salidas: la venta,
la anulación, la devolución, la transferencia, el ajuste y las salidas manuales (FEFO: vence primero, sale primero; «sin lote» último; un
vencido se vende con aviso). Este archivo prueba ese cableado de punta a punta (sección «FEFO en VentaLibra»): marcar por el `PUT` del
producto, recibir con lote, `entrada` con lote, `plan-salida` antes de cobrar, la venta con `avisos`, la devolución (par devolución +
merma), la anulación, la transferencia, el ajuste, la baja de un lote (que estuvo deshabilitada hasta A-4, ADR-052, y se reactivó) y que
ninguna respuesta nueva lleva costos.

Los números del FEFO, a mano: la Leche tiene L-VENCIDO 4 (vencido hace 3 días), L-PRONTO 10 (vence en 5), L-LEJANO 6 (vence en 60) y 8 sin
lote. Vender 10 saca 4 de L-VENCIDO y 6 de L-PRONTO (queda en 4); el «sin lote» no se toca.
"""
import re
from datetime import date, timedelta

import pytest
from conftest import https_client
from motor_de_test import destino_dominio
from ventas_helpers import abrir_turno, crear_deposito, deposito_default, hoy, registrar_venta

from app import permisos
from app.costos import extras_de
from app.main import create_app

#: Costos que ninguna otra cifra del escenario repite: si aparecen en una respuesta, se filtraron.
COSTO = "731.42"
COSTO_DE_LA_RECEPCION = "543.21"

ROLES_SIN_ACCESO = ("staff", "vendedor", "cajero")
#: Las tres rutas de lectura, con `{p}` por el id del producto.
LECTURA = ("/api/vencimientos", "/api/vencimientos/export", "/api/vencimientos/productos/{p}/lotes")


def _entrar(admin_client, rol):
    """Un usuario de ese rol, logueado en la misma app que el admin."""
    creado = admin_client.post("/users", json={
        "username": f"u-{rol}", "name": rol.title(), "password": "clave-larga-1", "role": rol,
    })
    assert creado.status_code == 201, creado.text
    cliente = https_client(admin_client.app)
    assert cliente.post("/auth/login", json={"username": f"u-{rol}", "password": "clave-larga-1"}).status_code == 200
    return cliente


def _dia(dias: int) -> str:
    """La fecha de Argentina de hoy más `dias`, ISO."""
    return (date.fromisoformat(hoy()) + timedelta(days=dias)).isoformat()


def _movimientos(cliente, producto):
    """El ledger del producto, en orden, tal como está en la base."""
    filas = cliente.app.state.conn.execute(
        "SELECT movement_type, reason_code, quantity_delta, lot_code, expires_at, created_by, note "
        "FROM stock_movements WHERE item_id = ? ORDER BY id", (producto,),
    ).fetchall()
    return [tuple(f) for f in filas]


def _reporte(cliente, **params):
    r = cliente.get("/api/vencimientos", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _asignar(cliente, escenario, clave, **cambios):
    cuerpo = {
        "producto_id": escenario["leche"], "deposito_id": escenario["deposito"], "lote": "L-NUEVO", "vence": _dia(9),
        "cantidad": 3, "clave_operacion": clave, **cambios,
    }
    return cliente.post("/api/vencimientos/asignar", json=cuerpo)


def _merma(cliente, escenario, clave, **cambios):
    cuerpo = {
        "producto_id": escenario["leche"], "deposito_id": escenario["deposito"], "lote": "L-VENCIDO", "vence": _dia(-3),
        "cantidad": 4, "clave_operacion": clave, **cambios,
    }
    return cliente.post("/api/vencimientos/merma", json=cuerpo)


@pytest.fixture
def escenario(admin_client):
    """La Leche (marcada «vence» por el encargado, con costo), con tres lotes que entran por una recepción de compra que hace el
    encargado y 8 sin lote; y la Sal, sin marcar. Devuelve los clientes de cada rol y los ids."""
    c = admin_client
    c.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    assert c.post("/catalog/categories", json={"name": "Almacén"}).status_code == 200
    leche = c.post("/api/productos", json={
        "nombre": "Leche 1L", "unidad": "u", "precio_venta": "1500.00", "precio_costo": COSTO, "codigo": "LECHE-1",
        "categoria": "Almacén",
    })
    assert leche.status_code == 200, leche.text
    leche = leche.json()["id"]
    sal = c.post("/api/productos", json={
        "nombre": "Sal fina", "unidad": "u", "precio_venta": "900.00", "precio_costo": "400.00", "codigo": "SAL-1",
    }).json()["id"]
    deposito = deposito_default(c)
    clientes = {"admin": c, **{rol: _entrar(c, rol) for rol in ("encargado", "deposito", "vendedor", "cajero", "staff")}}
    encargado = clientes["encargado"]

    # El camino real: el encargado marca el producto y recibe la compra con lote y vencimiento (`compras.recibir`).
    marca = encargado.put(f"/api/vencimientos/productos/{leche}", json={"vence": True})
    assert marca.status_code == 200, marca.text
    proveedor = encargado.post("/api/proveedores", json={"nombre": "Distribuidora SA"}).json()["id"]
    recepcion = encargado.post("/api/purchase-receipts", json={"proveedor_id": proveedor}).json()["id"]
    for lote, dias, cantidad in (("L-VENCIDO", -3, 4), ("L-PRONTO", 5, 10), ("L-LEJANO", 60, 6)):
        linea = encargado.post(f"/api/purchase-receipts/{recepcion}/items", json={
            "item_id": leche, "quantity": str(cantidad), "unit_cost": COSTO_DE_LA_RECEPCION, "lot_code": lote,
            "expires_at": f"{_dia(dias)}T00:00:00",
        })
        assert linea.status_code == 200, linea.text
    confirmada = encargado.post(f"/api/purchase-receipts/{recepcion}/confirm", json={"deposito_id": deposito})
    assert confirmada.status_code == 200, confirmada.text
    # Y 8 sin lote, por el ajuste de entrada de siempre.
    assert c.post(f"/api/stock/{leche}/ajuste", json={
        "modo": "entrada", "cantidad": 8, "deposito_id": deposito, "referencia": "carga sin lote",
    }).status_code == 200
    assert c.post(f"/api/stock/{sal}/ajuste", json={
        "modo": "entrada", "cantidad": 20, "deposito_id": deposito, "referencia": "carga",
    }).status_code == 200
    return {"leche": leche, "sal": sal, "deposito": deposito, "clientes": clientes}


@pytest.fixture(params=["admin", "encargado", "deposito"])
def ve(request, escenario):
    """Un cliente de cada rol que tiene `vencimientos.ver`."""
    return escenario["clientes"][request.param]


@pytest.fixture(params=["admin", "encargado", "deposito"])
def mueve(request, escenario):
    """Un cliente de cada rol que tiene `vencimientos.mover`."""
    return escenario["clientes"][request.param]


# ── La revisión del motor está aplicada ──────────────────────────────────────


def test_la_instancia_de_pruebas_tiene_la_revision_0002_del_motor(admin_client):
    """La revisión `0002_vencimientos_lotes` de libracommerce v0.29.0 corre en la suite (`tests/conftest.py`, `_migrar_libracommerce`)
    como en un deploy (`libracommerce-migrar upgrade --prefijo ventalibra`): la columna del producto, el índice del ledger y la
    versión estampada. Sin ella el motor responde 503."""
    conn = admin_client.app.state.conn
    columnas = conn.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'catalog_items' AND column_name = 'tracks_expiry'"
    ).fetchall()
    assert [tuple(c) for c in columnas] == [("tracks_expiry", "integer", "NO")]
    indices = conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'stock_movements' AND indexname = 'idx_stock_item_location_lot'"
    ).fetchall()
    assert len(indices) == 1 and "(item_id, location_id, lot_code)" in indices[0][0]
    # La cabeza de la cadena del motor: la 0002 sigue verificada arriba (columna e índice); la 0003 (v0.32.0, plazo y techo de reposición,
    # ADR-055) agrega sus dos columnas, la 0004 (v0.33.0, proveedor habitual, ADR-056) la suya y la 0005 (v0.36.0, mínimo por sucursal, ADR-059) su tabla.
    assert [tuple(v) for v in conn.execute("SELECT version_num FROM alembic_version_libracommerce").fetchall()] == [
        ("0005_min_stock_por_sucursal",)]
    propias = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'catalog_items' "
        "AND column_name IN ('lead_time_days', 'max_stock', 'supplier_party_id') ORDER BY column_name"
    ).fetchall()
    assert [c[0] for c in propias] == ["lead_time_days", "max_stock", "supplier_party_id"]


def test_sin_la_revision_el_motor_contesta_503_con_el_comando(tmp_path):
    """Una instancia que sólo arrancó (`create_app()` corre la baseline congelada, no la 0002) no tiene la columna: el motor lo dice
    con un 503 y el comando que falta, en vez de romper. Es lo que pasaría en un deploy que no declarara la migración."""
    with https_client(create_app(destino_dominio(tmp_path / "ventalibra.db"))) as client:
        assert client.post("/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200
        r = client.get("/api/vencimientos")
        assert r.status_code == 503, r.text
        assert "libracommerce-migrar upgrade" in r.json()["detail"]


# ── Marcar un producto ───────────────────────────────────────────────────────


def test_el_encargado_marca_y_desmarca_un_producto_y_no_toca_el_ledger(escenario):
    encargado = escenario["clientes"]["encargado"]
    antes = _movimientos(encargado, escenario["sal"])
    r = encargado.put(f"/api/vencimientos/productos/{escenario['sal']}", json={"vence": True})
    assert r.status_code == 200 and r.json() == {"producto_id": escenario["sal"], "vence": True}
    ficha = encargado.get(f"/api/vencimientos/productos/{escenario['sal']}/lotes").json()["producto"]
    assert ficha["vence"] is True and ficha["codigo"] == "SAL-1"
    assert encargado.put(f"/api/vencimientos/productos/{escenario['sal']}", json={"vence": False}).json()["vence"] is False
    assert _movimientos(encargado, escenario["sal"]) == antes


def test_el_deposito_no_marca_y_nadie_de_mostrador_tampoco(escenario):
    """`vencimientos.marcar` es sólo del encargado (y el admin). El rechazo es por rol (403 «forbidden») aunque el cuerpo sea válido
    y no cambia nada."""
    for rol in ("deposito",) + ROLES_SIN_ACCESO:
        r = escenario["clientes"][rol].put(f"/api/vencimientos/productos/{escenario['sal']}", json={"vence": True})
        assert r.status_code == 403 and r.json()["detail"] == "forbidden", (rol, r.text)
    ficha = escenario["clientes"]["admin"].get(f"/api/vencimientos/productos/{escenario['sal']}/lotes").json()["producto"]
    assert ficha["vence"] is False
    assert escenario["clientes"]["admin"].put(f"/api/vencimientos/productos/{escenario['sal']}", json={"vence": True}).status_code == 200


def test_un_producto_sin_marcar_no_se_asigna_ni_aparece_en_el_reporte(escenario):
    encargado = escenario["clientes"]["encargado"]
    r = _asignar(encargado, escenario, "sal-1", producto_id=escenario["sal"])
    assert r.status_code == 409, r.text
    assert all(f["producto_id"] != escenario["sal"] for f in _reporte(encargado, dias=365)["lotes"])


# ── El reporte ───────────────────────────────────────────────────────────────


def test_el_reporte_trae_el_lote_por_vencer_el_vencido_y_el_sin_lote(ve, escenario):
    m = _reporte(ve)
    assert (m["dias"], m["incluir_vencidos"], m["hoy"], m["hasta"]) == (15, True, hoy(), _dia(15))
    por_lote = {f["lote"]: f for f in m["lotes"]}
    assert set(por_lote) == {"L-VENCIDO", "L-PRONTO"}  # el de 60 días queda fuera de la ventana
    assert (por_lote["L-VENCIDO"]["estado"], por_lote["L-VENCIDO"]["dias_para_vencer"], por_lote["L-VENCIDO"]["saldo"]) == ("vencido", -3, 4)
    assert (por_lote["L-PRONTO"]["estado"], por_lote["L-PRONTO"]["dias_para_vencer"], por_lote["L-PRONTO"]["saldo"]) == ("por_vencer", 5, 10)
    assert por_lote["L-PRONTO"]["vence"] == _dia(5) and por_lote["L-PRONTO"]["codigo"] == "LECHE-1"
    (sin,) = m["sin_lote"]
    assert (sin["producto_id"], sin["saldo"], sin["situacion"]) == (escenario["leche"], 8, "sin_fecha")
    assert m["resumen"]["lotes_por_vencer"] == 1 and m["resumen"]["lotes_vencidos"] == 1
    assert m["resumen"]["unidades_por_vencer"] == 10 and m["resumen"]["unidades_vencidas"] == 4
    # La ventana es un parámetro: con 90 días entra el de 60; sin vencidos, se va el vencido.
    assert {f["lote"] for f in _reporte(ve, dias=90)["lotes"]} == {"L-VENCIDO", "L-PRONTO", "L-LEJANO"}
    assert {f["lote"] for f in _reporte(ve, incluir_vencidos="false")["lotes"]} == {"L-PRONTO"}


def test_los_lotes_de_un_producto_incluyen_el_bucket_sin_lote(ve, escenario):
    r = ve.get(f"/api/vencimientos/productos/{escenario['leche']}/lotes")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["producto"]["vence"] is True and cuerpo["producto"]["codigo"] == "LECHE-1"
    saldos = {(f["lote"], f["sin_lote"]): f["saldo"] for f in cuerpo["lotes"]}
    assert saldos == {("L-VENCIDO", False): 4, ("L-PRONTO", False): 10, ("L-LEJANO", False): 6, (None, True): 8}
    assert ve.get("/api/vencimientos/productos/999999/lotes").status_code == 404


def test_el_export_csv_bajo_el_mismo_prefijo(ve, escenario):
    r = ve.get("/api/vencimientos/export")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lineas = r.text.splitlines()
    assert lineas[0].startswith("producto_id,codigo,nombre,")
    assert len(lineas) == 3 and any("L-PRONTO" in linea for linea in lineas)


def test_los_filtros_de_sucursal_y_de_categoria(admin_client, escenario):
    sucursal = admin_client.get("/api/sucursales").json()[0]["id"]
    assert len(_reporte(admin_client, sucursal_id=sucursal, categoria="Almacén")["lotes"]) == 2
    assert _reporte(admin_client, categoria="Otra")["lotes"] == []
    assert admin_client.get("/api/vencimientos", params={"sucursal_id": 999999}).status_code == 422
    assert admin_client.get("/api/vencimientos", params={"dias": 0}).status_code == 422


@pytest.mark.parametrize("rol", ROLES_SIN_ACCESO)
def test_staff_vendedor_y_cajero_no_ven_nada(escenario, rol):
    cliente = escenario["clientes"][rol]
    for ruta in LECTURA:
        r = cliente.get(ruta.format(p=escenario["leche"]))
        assert r.status_code == 403 and r.json()["detail"] == "forbidden", (rol, ruta, r.text)


def test_sin_sesion_es_401_en_las_seis_rutas(escenario):
    anonimo = https_client(escenario["clientes"]["admin"].app)
    p = escenario["leche"]
    for ruta in LECTURA:
        assert anonimo.get(ruta.format(p=p)).status_code == 401, ruta
    assert anonimo.put(f"/api/vencimientos/productos/{p}", json={"vence": True}).status_code == 401
    assert _asignar(anonimo, escenario, "anonimo-1").status_code == 401
    assert _merma(anonimo, escenario, "anonimo-2").status_code == 401


# ── Asignar un vencimiento y dar de baja un lote ─────────────────────────────


def test_el_encargado_y_el_deposito_asignan_un_vencimiento_a_lo_que_no_tiene(mueve, escenario):
    """Un par aditivo: sale de «sin lote» y entra al lote nuevo, a nombre de quien lo hizo; el stock total no cambia."""
    antes = _movimientos(mueve, escenario["leche"])
    quien = int(mueve.get("/auth/me").json()["id"])
    r = _asignar(mueve, escenario, "asignar-1")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["lote"], cuerpo["vence"], cuerpo["cantidad"], cuerpo["saldo_sin_lote"], cuerpo["repetida"]) == (
        "L-NUEVO", _dia(9), 3, 5, False)
    nuevos = _movimientos(mueve, escenario["leche"])[len(antes):]
    assert len(nuevos) == 2 and sum(float(f[2]) for f in nuevos) == 0
    assert {f[5] for f in nuevos} == {quien}  # `created_by`: el usuario de la sesión, con id entero
    assert sorted((f[3], float(f[2])) for f in nuevos if f[3]) == [("L-NUEVO", 3.0)]
    assert {f["lote"]: f["saldo"] for f in _reporte(mueve)["lotes"]}["L-NUEVO"] == 3
    assert _reporte(mueve)["sin_lote"][0]["saldo"] == 5
    assert float(mueve.get(f"/api/stock/{escenario['leche']}").json()["stock_actual"]) == 28


def test_el_mostrador_no_asigna_ni_da_de_baja(escenario):
    antes = _movimientos(escenario["clientes"]["admin"], escenario["leche"])
    for rol in ROLES_SIN_ACCESO:
        for r in (_asignar(escenario["clientes"][rol], escenario, f"x-{rol}-a"),
                  _merma(escenario["clientes"][rol], escenario, f"x-{rol}-m")):
            assert r.status_code == 403 and r.json()["detail"] == "forbidden", (rol, r.text)
    assert _movimientos(escenario["clientes"]["admin"], escenario["leche"]) == antes


def test_dar_de_baja_un_lote_vencido_es_una_merma_a_nombre_de_quien_la_hizo(mueve, escenario):
    quien = int(mueve.get("/auth/me").json()["id"])
    antes = _movimientos(mueve, escenario["leche"])
    r = _merma(mueve, escenario, "merma-1")
    assert r.status_code == 200, r.text
    assert (r.json()["saldo_restante"], r.json()["cantidad"], r.json()["repetida"]) == (0, 4, False)
    (nuevo,) = _movimientos(mueve, escenario["leche"])[len(antes):]
    assert nuevo[0] == "waste" and float(nuevo[2]) == -4 and nuevo[3] == "L-VENCIDO" and nuevo[5] == quien
    assert "Vencimiento" in nuevo[6]
    assert {f["lote"] for f in _reporte(mueve)["lotes"]} == {"L-PRONTO"}  # el vencido ya no está
    # No se puede dar de baja más de lo que hay ni dejar un lote negativo.
    r = _merma(mueve, escenario, "merma-2", cantidad=1)
    assert r.status_code == 409, r.text


def test_un_reintento_con_la_misma_clave_no_vuelve_a_escribir(mueve, escenario):
    """La idempotencia es del motor (`clave_operacion`), acá se prueba que llega por el camino real: la respuesta del reintento es
    la de la primera vez con `repetida: true`, y el ledger tiene UN solo movimiento (o un solo par) de esa operación."""
    antes = len(_movimientos(mueve, escenario["leche"]))
    primera = _merma(mueve, escenario, "misma-clave")
    assert primera.status_code == 200 and primera.json()["repetida"] is False
    segunda = _merma(mueve, escenario, "misma-clave")
    assert segunda.status_code == 200, segunda.text
    assert segunda.json() == {**primera.json(), "repetida": True}
    assert len(_movimientos(mueve, escenario["leche"])) == antes + 1
    # Lo mismo con la asignación: un par, una sola vez.
    par = _asignar(mueve, escenario, "misma-clave-2")
    reintento = _asignar(mueve, escenario, "misma-clave-2")
    assert par.json()["repetida"] is False and reintento.json()["repetida"] is True
    assert len(_movimientos(mueve, escenario["leche"])) == antes + 1 + 2
    # La misma clave con otros datos no es un reintento: 409, y tampoco escribe.
    assert _asignar(mueve, escenario, "misma-clave-2", cantidad=1).status_code == 409
    assert len(_movimientos(mueve, escenario["leche"])) == antes + 1 + 2


def test_cuerpos_invalidos_son_422_y_no_escriben(admin_client, escenario):
    antes = _movimientos(admin_client, escenario["leche"])
    assert _asignar(admin_client, escenario, "").status_code == 422  # la clave es obligatoria
    assert _asignar(admin_client, escenario, "k", cantidad=0).status_code == 422
    assert _asignar(admin_client, escenario, "k", deposito_id=999999).status_code == 422
    assert _merma(admin_client, escenario, "k", cantidad=-1).status_code == 422
    assert admin_client.put(f"/api/vencimientos/productos/{escenario['leche']}", json={"vence": "si"}).status_code == 422
    assert admin_client.put("/api/vencimientos/productos/999999", json={"vence": True}).status_code == 404
    assert _movimientos(admin_client, escenario["leche"]) == antes


# ── FEFO en VentaLibra (ADR-053, libracommerce v0.30.0) ──────────────────────


def _saldos(cliente, **params):
    """`{lote: saldo}` del reporte (sólo lo que tiene saldo > 0) y el saldo «sin lote» (`None` si no hay fila)."""
    m = _reporte(cliente, **{"dias": 90, **params})
    return {f["lote"]: f["saldo"] for f in m["lotes"]}, (m["sin_lote"][0]["saldo"] if m["sin_lote"] else None)


def _stock(cliente, producto, deposito=None):
    r = cliente.get(f"/api/stock/{producto}", params={"deposito_id": deposito} if deposito else {})
    assert r.status_code == 200, r.text
    return float(r.json()["stock_deposito" if deposito else "stock_actual"])


def _plan(cliente, escenario, qty, **cambios):
    cuerpo = {"items": [{"producto_id": escenario["leche"], "qty": qty}], "deposito_id": escenario["deposito"], **cambios}
    return cliente.post("/api/ventas/plan-salida", json=cuerpo)


def _linea_de_la_venta(cliente, venta_id):
    return cliente.app.state.conn.execute("SELECT id FROM sale_items WHERE sale_id = ? ORDER BY id LIMIT 1", (venta_id,)).fetchone()[0]


def _filas(cliente, producto, desde=0):
    """Lo que el ledger escribió desde la fila `desde`: `(tipo, código, delta, lote)`."""
    return [(f[0], f[1], float(f[2]), f[3]) for f in _movimientos(cliente, producto)[desde:]]


def test_un_producto_sin_marcar_no_cambia_nada_en_el_ledger_de_una_venta(admin_client, escenario):
    """La Sal no está marcada: su venta escribe el movimiento de siempre, sin lote ni vencimiento, y no aparece en ningún reporte.
    (No se tocó el camino de ventas: lo que se prueba es que el motor nuevo no lo cambia.)"""
    abrir_turno(admin_client)
    antes = _movimientos(admin_client, escenario["sal"])
    venta = registrar_venta(admin_client, escenario["sal"], precio="900.00", cantidad="2")
    (fila,) = _movimientos(admin_client, escenario["sal"])[len(antes):]
    assert (float(fila[2]), fila[3], fila[4]) == (-2.0, None, None)
    assert fila[0] != "waste"
    assert all(f["producto_id"] != escenario["sal"] for f in _reporte(admin_client, dias=365)["lotes"] + _reporte(admin_client)["sin_lote"])
    assert "avisos" not in venta  # sin marcados, la respuesta es la de siempre


def test_una_venta_de_un_producto_marcado_descuenta_por_fefo_y_el_sin_lote_queda_intacto(admin_client, escenario):
    """La conducta de A-4, medida: la venta resta del lote que vence primero (el vencido, y después el que sigue) y no del «sin lote»,
    que se vende último. Era el test que fijaba la limitación de ADR-052 (8 sin lote, se venden 10: -2 sin lote y los lotes enteros)."""
    abrir_turno(admin_client)
    venta = registrar_venta(admin_client, escenario["leche"], precio="1500.00", cantidad="10")
    lotes, sin_lote = _saldos(admin_client)
    assert lotes == {"L-PRONTO": 4, "L-LEJANO": 6}  # L-VENCIDO 4 -> 0 y L-PRONTO 10 -> 4: 4 + 6 = 10
    assert sin_lote == 8  # intacto, sin el «salidas_sin_lote» de antes
    m = _reporte(admin_client)
    assert m["sin_lote"][0]["situacion"] == "sin_fecha" and m["resumen"]["productos_con_salidas_sin_lote"] == 0
    assert _filas(admin_client, escenario["leche"], 4) == [("sale", "venta", -4.0, "L-VENCIDO"), ("sale", "venta", -6.0, "L-PRONTO")]
    assert _stock(admin_client, escenario["leche"]) == 18
    # El aviso de lote vencido (y el de por vencer) viaja en la respuesta de la venta y en su detalle.
    assert [(a["tipo"], a["lote"], a["cantidad"], a["dias_para_vencer"]) for a in venta["avisos"]] == [
        ("lote_vencido", "L-VENCIDO", 4, -3), ("por_vencer", "L-PRONTO", 6, 5)]
    assert all(a["nombre"] == "Leche 1L" and a["producto_id"] == escenario["leche"] for a in venta["avisos"])
    assert admin_client.get(f"/api/ventas/{venta['id']}").json()["avisos"] == venta["avisos"]


def test_una_venta_con_todo_vigente_no_trae_avisos(admin_client, escenario):
    """La clave `avisos` sólo existe si hay algo que avisar: L-LEJANO vence en 60 días (fuera de la ventana de 15)."""
    abrir_turno(admin_client)
    for lote, qty in (("L-VENCIDO", 4), ("L-PRONTO", 10)):
        r = admin_client.post("/api/vencimientos/merma", json={
            "producto_id": escenario["leche"], "deposito_id": escenario["deposito"], "lote": lote,
            "vence": _dia(-3 if lote == "L-VENCIDO" else 5), "cantidad": qty, "clave_operacion": f"baja-{lote}"})
        assert r.status_code == 200, r.text
    venta = registrar_venta(admin_client, escenario["leche"], precio="1500.00", cantidad="2")
    assert "avisos" not in venta
    assert _saldos(admin_client)[0] == {"L-LEJANO": 4}
    assert "avisos" not in admin_client.get(f"/api/ventas/{venta['id']}").json()


def test_el_plan_de_salida_dice_de_que_lote_saldria_y_no_escribe_nada(escenario):
    """`POST /api/ventas/plan-salida` es lectura pura: el POS lo consulta antes de cobrar. Mismo plan que después hace la venta."""
    cajero = escenario["clientes"]["cajero"]
    antes = _movimientos(cajero, escenario["leche"])
    r = _plan(cajero, escenario, 10)
    assert r.status_code == 200, r.text
    plan = r.json()
    assert (plan["hoy"], plan["dias"]) == (hoy(), 15)
    assert [(s["lote"], s["cantidad"], s["estado"], s["dias_para_vencer"], s["faltante"]) for s in plan["salidas"]] == [
        ("L-VENCIDO", 4, "vencido", -3, 0), ("L-PRONTO", 6, "vigente", 5, 0)]
    assert [(a["tipo"], a["lote"], a["vence"]) for a in plan["avisos"]] == [
        ("lote_vencido", "L-VENCIDO", _dia(-3)), ("por_vencer", "L-PRONTO", _dia(5))]
    assert _movimientos(cajero, escenario["leche"]) == antes and _stock(cajero, escenario["leche"]) == 28
    # Lo que no alcanza sale del «sin lote» (8) y el resto es faltante; un producto sin marcar no elige lote.
    plan = _plan(cajero, escenario, 30).json()
    assert [(s["lote"], s["cantidad"], s["estado"], s["faltante"]) for s in plan["salidas"]] == [
        ("L-VENCIDO", 4, "vencido", 0), ("L-PRONTO", 10, "vigente", 0), ("L-LEJANO", 6, "vigente", 0), (None, 10, "sin_lote", 2)]
    sal = cajero.post("/api/ventas/plan-salida", json={"items": [{"producto_id": escenario["sal"], "qty": 3}]})
    assert sal.status_code == 200 and sal.json()["salidas"] == [] and sal.json()["avisos"] == []
    # Cuerpos inválidos: 422 y nada escrito.
    assert cajero.post("/api/ventas/plan-salida", json={"items": []}).status_code == 422
    assert _plan(cajero, escenario, 0).status_code == 422
    assert _plan(cajero, escenario, 1, deposito_id=999999).status_code == 422
    assert cajero.post("/api/ventas/plan-salida", json={"items": [{"producto_id": 999999, "qty": 1}]}).status_code == 422
    assert _movimientos(cajero, escenario["leche"]) == antes


def test_quien_puede_vender_puede_consultar_el_plan_y_el_resto_no(escenario):
    """La capacidad es la del POS (`ventas.pos`): encargado, vendedor, cajero, staff y admin; el depósito no vende y el anónimo, 401."""
    for rol in ("admin", "encargado", "vendedor", "cajero", "staff"):
        assert _plan(escenario["clientes"][rol], escenario, 1).status_code == 200, rol
    r = _plan(escenario["clientes"]["deposito"], escenario, 1)
    assert r.status_code == 403 and r.json()["detail"] == "forbidden"
    assert _plan(https_client(escenario["clientes"]["admin"].app), escenario, 1).status_code == 401


def test_la_devolucion_de_un_marcado_es_un_par_devolucion_y_merma_por_lote_y_el_neto_es_cero(admin_client, escenario):
    """Decisión de producto 3: la devolución de un perecedero va a merma, no vuelve al lote. Se vendieron 4 de L-VENCIDO y 6 de L-PRONTO
    y se devuelven 7: los 4 primeros al lote del que salieron y 3 del siguiente; cada tramo es `devolucion +q` y `merma -q`."""
    abrir_turno(admin_client)
    venta = registrar_venta(admin_client, escenario["leche"], precio="1500.00", cantidad="10")
    linea = _linea_de_la_venta(admin_client, venta["id"])
    antes = len(_movimientos(admin_client, escenario["leche"]))
    r = admin_client.post(f"/api/ventas/{venta['id']}/devolver", json={
        "lineas": [{"sale_item_id": linea, "cantidad": 7}], "deposito_id": escenario["deposito"]})
    assert r.status_code == 200 and r.json()["estado"] == "devuelta_parcial", r.text
    assert _filas(admin_client, escenario["leche"], antes) == [
        ("return", "devolucion", 4.0, "L-VENCIDO"), ("waste", "merma", -4.0, "L-VENCIDO"),
        ("return", "devolucion", 3.0, "L-PRONTO"), ("waste", "merma", -3.0, "L-PRONTO")]
    assert _saldos(admin_client) == ({"L-PRONTO": 4, "L-LEJANO": 6}, 8)  # el neto por lote es cero: lo devuelto no vuelve al estante
    assert _stock(admin_client, escenario["leche"]) == 18
    # No se puede devolver más de lo vendido (el tope sigue siendo por línea).
    r = admin_client.post(f"/api/ventas/{venta['id']}/devolver", json={
        "lineas": [{"sale_item_id": linea, "cantidad": 4}], "deposito_id": escenario["deposito"]})
    assert r.status_code == 422 and "quedan 3" in r.json()["detail"], r.text
    assert _stock(admin_client, escenario["leche"]) == 18


def test_anular_una_venta_de_un_marcado_repone_al_lote_del_que_salio(admin_client, escenario):
    abrir_turno(admin_client)
    venta = registrar_venta(admin_client, escenario["leche"], precio="1500.00", cantidad="10")
    assert _saldos(admin_client)[0] == {"L-PRONTO": 4, "L-LEJANO": 6}
    antes = len(_movimientos(admin_client, escenario["leche"]))
    r = admin_client.post(f"/api/ventas/{venta['id']}/anular")
    assert r.status_code == 200, r.text
    assert _filas(admin_client, escenario["leche"], antes) == [
        ("return", "anulacion", 4.0, "L-VENCIDO"), ("return", "anulacion", 6.0, "L-PRONTO")]
    assert _saldos(admin_client) == ({"L-VENCIDO": 4, "L-PRONTO": 10, "L-LEJANO": 6}, 8)
    assert _stock(admin_client, escenario["leche"]) == 28
    # Anular dos veces no repone dos veces.
    filas = len(_movimientos(admin_client, escenario["leche"]))
    assert admin_client.post(f"/api/ventas/{venta['id']}/anular").status_code == 200  # idempotente: responde la venta anulada
    assert len(_movimientos(admin_client, escenario["leche"])) == filas and _stock(admin_client, escenario["leche"]) == 28


def test_transferir_un_marcado_es_un_par_por_tramo_y_el_lote_viaja_al_destino(escenario):
    """12 unidades salen por FEFO del origen: 4 de L-VENCIDO y 8 de L-PRONTO, y cada tramo entra al destino con su lote y vencimiento."""
    deposito = escenario["clientes"]["deposito"]
    destino = crear_deposito(escenario["clientes"]["admin"], "Depósito chico")["id"]
    antes = len(_movimientos(deposito, escenario["leche"]))
    r = deposito.post("/api/depositos/transferir", json={
        "producto_id": escenario["leche"], "origen_id": escenario["deposito"], "destino_id": destino, "cantidad": 12})
    assert r.status_code == 200, r.text
    filas = _movimientos(deposito, escenario["leche"])[antes:]
    assert [(float(f[2]), f[3], f[4]) for f in filas] == [
        (-4.0, "L-VENCIDO", _dia(-3)), (4.0, "L-VENCIDO", _dia(-3)), (-8.0, "L-PRONTO", _dia(5)), (8.0, "L-PRONTO", _dia(5))]
    saldos = deposito.app.state.conn.execute(
        "SELECT location_id, lot_code, SUM(quantity_delta) FROM stock_movements WHERE item_id = ? AND lot_code IS NOT NULL "
        "GROUP BY location_id, lot_code ORDER BY location_id, lot_code", (escenario["leche"],)).fetchall()
    assert sorted((a, b, float(c)) for a, b, c in saldos) == sorted([
        (escenario["deposito"], "L-VENCIDO", 0.0), (escenario["deposito"], "L-PRONTO", 2.0), (escenario["deposito"], "L-LEJANO", 6.0),
        (destino, "L-VENCIDO", 4.0), (destino, "L-PRONTO", 8.0)])
    assert _stock(deposito, escenario["leche"]) == 28  # una transferencia no cambia el total


def test_ajustar_un_marcado_sigue_el_lote(admin_client, escenario):
    """El ajuste del total (baja por FEFO) y la salida manual (FEFO). El conteo de UN lote por este endpoint no está habilitado
    (`OpcionesStock.con_lotes` apagada, ADR-053): ver `test_el_ajuste_de_stock_no_acepta_lote_para_ningun_rol`."""
    leche, dep = escenario["leche"], escenario["deposito"]
    # Llevar el total de 28 a 20 sin indicar lote: baja 8 por FEFO (los 4 del vencido y 4 de L-PRONTO), no del «sin lote».
    antes = len(_movimientos(admin_client, leche))
    r = admin_client.post(f"/api/stock/{leche}/ajuste", json={"modo": "absoluto", "cantidad": 20, "deposito_id": dep, "referencia": "conteo"})
    assert r.status_code == 200, r.text
    assert _filas(admin_client, leche, antes) == [("adjustment", "ajuste", -4.0, "L-VENCIDO"), ("adjustment", "ajuste", -4.0, "L-PRONTO")]
    # Una salida manual también sale por lote: 2 más de L-PRONTO.
    antes = len(_movimientos(admin_client, leche))
    r = admin_client.post(f"/api/stock/{leche}/ajuste", json={"modo": "salida", "cantidad": 2, "deposito_id": dep, "referencia": "rotura"})
    assert r.status_code == 200, r.text
    assert _filas(admin_client, leche, antes) == [("adjustment", "salida", -2.0, "L-PRONTO")]
    assert _saldos(admin_client) == ({"L-PRONTO": 4, "L-LEJANO": 6}, 8) and _stock(admin_client, leche) == 18
    # Un producto sin marcar sigue ajustándose como siempre.
    sal = escenario["sal"]
    antes = len(_movimientos(admin_client, sal))
    assert admin_client.post(f"/api/stock/{sal}/ajuste", json={"modo": "absoluto", "cantidad": 15, "deposito_id": dep}).status_code == 200
    assert _filas(admin_client, sal, antes) == [("adjustment", "ajuste", -5.0, None)]


@pytest.mark.parametrize("rol", ["admin", "encargado", "deposito", "staff"])
def test_el_ajuste_de_stock_no_acepta_lote_para_ningun_rol(escenario, rol):
    """`OpcionesStock.con_lotes` está APAGADA (ADR-053): `POST /api/stock/{id}/ajuste` no maneja lotes. Con la opción apagada el cuerpo es el de
    siempre y el motor IGNORA `lot_code` y `expires_at` (pydantic descarta lo que no declara): no se crea ni se toca ningún lote por esa
    ruta, ni siquiera por el staff heredado, que tiene `stock.ajustar` pero NO `vencimientos.mover` (la carga con lote es sólo
    `POST /api/vencimientos/entrada`). Lo que se escribe es la entrada de siempre, SIN lote, y el reporte no ve ningún lote nuevo."""
    leche, dep = escenario["leche"], escenario["deposito"]
    cliente = escenario["clientes"][rol]
    admin = escenario["clientes"]["admin"]
    lotes_antes = _saldos(admin)
    antes = len(_movimientos(admin, leche))
    r = cliente.post(f"/api/stock/{leche}/ajuste", json={
        "modo": "entrada", "cantidad": 5, "deposito_id": dep, "lot_code": "L-COLADO", "expires_at": _dia(30), "referencia": "carga"})
    assert r.status_code == 200, (rol, r.text)
    (fila,) = _movimientos(admin, leche)[antes:]
    assert (fila[1], float(fila[2]), fila[3], fila[4]) == ("entrada", 5.0, None, None), (rol, fila)  # sin lote ni vencimiento
    lotes, sin_lote = _saldos(admin)
    assert "L-COLADO" not in lotes and lotes == lotes_antes[0] and sin_lote == lotes_antes[1] + 5
    # El camino con lote es el de vencimientos: el staff no entra (403); los demás sí.
    cuerpo = {"producto_id": leche, "deposito_id": dep, "lote": "L-COLADO", "vence": _dia(30), "cantidad": 1, "clave_operacion": f"carga-{rol}"}
    r = cliente.post("/api/vencimientos/entrada", json=cuerpo)
    assert r.status_code == (403 if rol == "staff" else 200), (rol, r.text)
    assert ("L-COLADO" in _saldos(admin)[0]) == (rol != "staff")


def test_un_marcado_con_stock_por_variante_exige_la_variante_en_el_ajuste(admin_client, escenario):
    """Hallazgo de Codex sobre el motor, medido acá: sin variante el ajuste de un marcado con stock en una variante es 422 y no escribe."""
    leche, dep = escenario["leche"], escenario["deposito"]
    variante = admin_client.post(f"/api/productos/{leche}/variantes", json={"sku": "LECHE-ENT", "nombre": "Entera"})
    assert variante.status_code == 200, variante.text
    vid = variante.json()["id"]
    assert admin_client.post(f"/api/stock/{leche}/ajuste", json={
        "modo": "entrada", "cantidad": 5, "deposito_id": dep, "variant_id": vid}).status_code == 200
    antes = _movimientos(admin_client, leche)
    r = admin_client.post(f"/api/stock/{leche}/ajuste", json={"modo": "salida", "cantidad": 1, "deposito_id": dep})
    assert r.status_code == 422 and "variante" in r.json()["detail"], r.text
    assert _movimientos(admin_client, leche) == antes


def test_cargar_stock_con_lote_por_entrada(mueve, escenario):
    """`POST /api/vencimientos/entrada` (`vencimientos.mover`: encargado y depósito): stock
    nuevo en ESE lote, a nombre de quien lo cargó; un reintento con la misma clave no vuelve a sumar."""
    leche, dep = escenario["leche"], escenario["deposito"]
    quien = int(mueve.get("/auth/me").json()["id"])
    cuerpo = {"producto_id": leche, "deposito_id": dep, "lote": "L-NUEVO", "vence": _dia(20), "cantidad": 12, "clave_operacion": "entrada-1"}
    antes = len(_movimientos(mueve, leche))
    r = mueve.post("/api/vencimientos/entrada", json=cuerpo)
    assert r.status_code == 200, r.text
    assert (r.json()["lote"], r.json()["cantidad"], r.json()["saldo_lote"], r.json()["repetida"]) == ("L-NUEVO", 12, 12, False)
    (fila,) = _movimientos(mueve, leche)[antes:]
    assert (fila[0], fila[1], float(fila[2]), fila[3], fila[4], fila[5]) == ("adjustment", "entrada", 12.0, "L-NUEVO", _dia(20), quien)
    assert mueve.post("/api/vencimientos/entrada", json=cuerpo).json()["repetida"] is True
    assert len(_movimientos(mueve, leche)) == antes + 1 and _stock(mueve, leche) == 40
    assert _saldos(mueve)[0]["L-NUEVO"] == 12
    # Sin marcar, con una clave vacía o una cantidad cero: no escribe.
    assert mueve.post("/api/vencimientos/entrada", json={**cuerpo, "producto_id": escenario["sal"], "clave_operacion": "x"}).status_code == 409
    assert mueve.post("/api/vencimientos/entrada", json={**cuerpo, "clave_operacion": ""}).status_code == 422
    assert mueve.post("/api/vencimientos/entrada", json={**cuerpo, "clave_operacion": "y", "cantidad": 0}).status_code == 422
    assert len(_movimientos(mueve, leche)) == antes + 1


def test_el_mostrador_no_carga_stock_con_lote(escenario):
    antes = _movimientos(escenario["clientes"]["admin"], escenario["leche"])
    for rol in ROLES_SIN_ACCESO:
        r = escenario["clientes"][rol].post("/api/vencimientos/entrada", json={
            "producto_id": escenario["leche"], "deposito_id": escenario["deposito"], "lote": "L-X", "vence": _dia(9),
            "cantidad": 1, "clave_operacion": f"e-{rol}"})
        assert r.status_code == 403 and r.json()["detail"] == "forbidden", (rol, r.text)
    assert _movimientos(escenario["clientes"]["admin"], escenario["leche"]) == antes


def test_la_baja_de_un_lote_funciona_y_la_guarda_del_motor_sigue_con_un_sin_lote_negativo_heredado(escenario):
    """La merma se reactivó (200). La guarda del motor sigue: con un saldo «sin lote» NEGATIVO en ese depósito (lo que dejan las ventas de
    antes de A-4, o un faltante) no se puede dar de baja ningún lote hasta conciliar con el conteo físico: 409, sin escribir."""
    admin, encargado = escenario["clientes"]["admin"], escenario["clientes"]["encargado"]
    leche, dep = escenario["leche"], escenario["deposito"]
    assert _merma(encargado, escenario, "baja-1").status_code == 200  # L-VENCIDO: 4 -> 0
    # Se deja el «sin lote» en negativo: se vende todo lo que hay (24) y 2 más que no tienen respaldo (faltante).
    abrir_turno(admin)
    venta = registrar_venta(admin, leche, precio="1500.00", cantidad="26")
    assert [a["tipo"] for a in venta["avisos"]] == ["por_vencer", "faltante_sin_lote"]
    lotes, sin_lote = _saldos(admin)
    assert lotes == {} and sin_lote == -2
    assert admin.post("/api/vencimientos/entrada", json={
        "producto_id": leche, "deposito_id": dep, "lote": "L-REPO", "vence": _dia(40), "cantidad": 10, "clave_operacion": "repo"}).status_code == 200
    antes = _movimientos(admin, leche)
    r = _merma(encargado, escenario, "baja-2", lote="L-REPO", vence=_dia(40), cantidad=3)
    assert r.status_code == 409 and "sin lote" in r.json()["detail"], r.text
    assert _movimientos(admin, leche) == antes
    # Conciliado el «sin lote» (un ajuste del bucket que lo lleva a cero), la baja pasa.
    assert admin.post(f"/api/stock/{leche}/ajuste", json={
        "modo": "entrada", "cantidad": 2, "deposito_id": dep, "referencia": "conteo físico"}).status_code == 200
    assert _saldos(admin)[1] == 0 or _saldos(admin)[1] is None
    assert _merma(encargado, escenario, "baja-3", lote="L-REPO", vence=_dia(40), cantidad=3).status_code == 200


def test_marcar_un_producto_por_el_put_del_producto_es_del_encargado(escenario):
    """El `PUT /api/productos/{id}` con `vence` (la marca en la ficha del producto, libra-ui v0.92.0) la decide `vencimientos.marcar`, no
    `productos.escribir`: el staff heredado edita productos pero no puede marcar (403 y NO se guarda nada de la edición); el encargado y el
    admin sí. Sin `vence` la edición no toca la marca."""
    sal, admin, encargado, staff = escenario["sal"], escenario["clientes"]["admin"], escenario["clientes"]["encargado"], escenario["clientes"]["staff"]
    ficha = {"nombre": "Sal fina", "unidad": "u", "precio_venta": "950.00", "precio_costo": "400.00", "codigo": "SAL-1"}

    def vence(cliente):
        return next(p for p in cliente.get("/api/productos").json() if p["id"] == sal)["vence"]

    assert vence(admin) is False
    r = staff.put(f"/api/productos/{sal}", json={**ficha, "vence": True})
    assert r.status_code == 403 and "marcar" in r.json()["detail"], r.text
    assert next(p for p in admin.get("/api/productos").json() if p["id"] == sal)["precio_venta"] == 900  # no guardó el resto
    # El staff edita el producto sin tocar la marca (o repitiéndola): 200.
    assert staff.put(f"/api/productos/{sal}", json={**ficha, "vence": False}).status_code == 200
    assert staff.put(f"/api/productos/{sal}", json=ficha).status_code == 200
    # El encargado marca por ahí, la respuesta ya trae `vence`, y por el PUT de vencimientos se ve lo mismo.
    r = encargado.put(f"/api/productos/{sal}", json={**ficha, "vence": True})
    assert r.status_code == 200 and r.json()["vence"] is True, r.text
    assert vence(admin) is True
    assert admin.get(f"/api/vencimientos/productos/{sal}/lotes").json()["producto"]["vence"] is True
    # Editar sin `vence` no la pierde; el admin la saca.
    assert encargado.put(f"/api/productos/{sal}", json={**ficha, "precio_venta": "1000.00"}).status_code == 200 and vence(admin) is True
    assert admin.put(f"/api/productos/{sal}", json={**ficha, "vence": False}).json()["vence"] is False
    # Un servicio no se marca.
    servicio = admin.post("/api/productos", json={"nombre": "Envío", "unidad": "u", "precio_venta": "100.00", "tipo": "servicio"})
    assert servicio.status_code == 200, servicio.text
    r = admin.put(f"/api/productos/{servicio.json()['id']}", json={
        "nombre": "Envío", "unidad": "u", "precio_venta": "100.00", "tipo": "servicio", "vence": True})
    assert r.status_code == 409, r.text


def test_todos_los_roles_que_leen_productos_reciben_vence(escenario):
    """La pantalla del kit Productos muestra el interruptor «Vence» sólo si el listado lo trae: lo leen los roles con `catalogo.ver`."""
    for rol, cliente in escenario["clientes"].items():
        productos = {p["nombre"]: p for p in cliente.get("/api/productos").json()}
        assert productos["Leche 1L"]["vence"] is True and productos["Sal fina"]["vence"] is False, rol


# ── Sin costos, sin gate de plan, y lo que pide la pantalla ──────────────────


def test_ningun_endpoint_de_vencimientos_revela_costos(escenario):
    """`/api/vencimientos` no está en los prefijos de `SinCostos` (`app/costos.py`): no hace falta si el endpoint no manda costos. Se
    prueba mirando lo que ve el ADMIN, que tiene `costos.ver` (el filtro no le sacaría nada aunque los hubiera): ni una clave con
    costo ni el valor del costo del producto (`precio_costo`) ni el de la recepción (`unit_cost`), en ninguna de las seis rutas. Y el
    depósito, que no tiene `costos.ver`, recibe exactamente lo mismo: el filtro no interviene."""
    assert extras_de("/api/vencimientos") is None and extras_de("/api/vencimientos/productos/1/lotes") is None
    assert not permisos.condicion("costos.ver")({"role": "deposito"})

    def claves(valor, ruta=""):
        if isinstance(valor, dict):
            for k, v in valor.items():
                if re.search(r"cost|margen|margin|subtotal|precio", k, re.I):
                    yield f"{ruta}/{k}"
                yield from claves(v, f"{ruta}/{k}")
        elif isinstance(valor, list):
            for v in valor:
                yield from claves(v, ruta)

    p = escenario["leche"]
    admin, deposito = escenario["clientes"]["admin"], escenario["clientes"]["deposito"]
    respuestas = []
    for cliente in (admin, deposito):
        for ruta in (*LECTURA, "/api/vencimientos?dias=365&incluir_vencidos=false"):
            r = cliente.get(ruta.format(p=p))
            assert r.status_code == 200, (ruta, r.text)
            respuestas.append((ruta, r))
    for ruta, r in respuestas:
        if r.headers["content-type"].startswith("application/json"):
            assert not list(claves(r.json())), (ruta, list(claves(r.json())))
        else:
            assert not re.search(r"cost|margen|margin|precio", r.text.splitlines()[0], re.I), ruta
        assert COSTO not in r.text and COSTO_DE_LA_RECEPCION not in r.text and "400.00" not in r.text, ruta
    # Las respuestas de escritura tampoco.
    for r in (_asignar(admin, escenario, "sc-1"), _merma(deposito, escenario, "sc-2"),
              admin.put(f"/api/vencimientos/productos/{p}", json={"vence": True})):
        assert r.status_code == 200, r.text
        assert not list(claves(r.json())) and COSTO not in r.text and COSTO_DE_LA_RECEPCION not in r.text
    # El depósito y el admin ven lo mismo (mismo JSON, campo por campo).
    assert admin.get("/api/vencimientos").json() == deposito.get("/api/vencimientos").json()


def test_las_respuestas_nuevas_de_fefo_no_revelan_costos_a_quien_no_tiene_costos_ver(escenario):
    """Los avisos de la venta, el plan de salida, la carga con lote y la marca `vence` del producto no llevan costos. `/api/ventas` y
    `/api/vencimientos` NO están en los prefijos de `SinCostos` (`app/costos.py`): no hace falta si el endpoint no manda costos, y acá se
    prueba que no los manda, por CLAVE (`cost`/`costo` como palabra, como el filtro) y por VALOR (los números que sólo el costo tiene),
    mirando lo que reciben el vendedor, el cajero y el depósito, que no tienen `costos.ver`. El contrapeso: el admin sí ve el costo en
    `/api/productos` (si el test no lo encontrara ahí, no estaría midiendo nada)."""
    leche, dep = escenario["leche"], escenario["deposito"]
    costos = (COSTO, COSTO_DE_LA_RECEPCION)  # 731.42 el del alta del producto y 543.21 el de la recepción (que pasa a ser `default_cost`)
    clave_de_costo = re.compile(r"(^|_)(costos?|cost)($|_)", re.I)

    def limpia(r, donde):
        assert r.status_code == 200, (donde, r.status_code, r.text)
        def claves(v):
            if isinstance(v, dict):
                for k, x in v.items():
                    if clave_de_costo.search(k):
                        yield k
                    yield from claves(x)
            elif isinstance(v, list):
                for x in v:
                    yield from claves(x)
        assert not list(claves(r.json())), (donde, list(claves(r.json())))
        assert not any(c in r.text for c in costos), (donde, r.text)
        return r.json()

    # El contrapeso: el admin ve el costo del producto donde corresponde.
    admin_ve = next(p for p in escenario["clientes"]["admin"].get("/api/productos").json() if p["id"] == leche)
    assert "precio_costo" in admin_ve and str(admin_ve["precio_costo"]) in (COSTO, COSTO_DE_LA_RECEPCION)

    for rol in ("vendedor", "cajero"):
        cliente = escenario["clientes"][rol]
        assert not permisos.condicion("costos.ver")({"role": rol})
        plan = limpia(_plan(cliente, escenario, 10), f"{rol} plan-salida")
        assert plan["avisos"] and plan["salidas"]  # hay qué mirar: no pasa por vacío
        productos = limpia(cliente.get("/api/productos"), f"{rol} productos")
        assert all("vence" in p and "precio_costo" not in p for p in productos)
    cajero = escenario["clientes"]["cajero"]
    abrir_turno(cajero)
    venta = limpia(cajero.post("/api/ventas", json={
        "fecha": hoy(), "items": [{"nombre": "Leche", "qty": 10, "precio": 1500.0, "producto_id": leche}],
        "pagos": [{"medio": "efectivo", "monto": 15000.0}]}), "cajero venta")
    assert venta["avisos"]
    limpia(cajero.get(f"/api/ventas/{venta['id']}"), "cajero detalle de la venta")
    deposito = escenario["clientes"]["deposito"]
    limpia(deposito.post("/api/vencimientos/entrada", json={
        "producto_id": leche, "deposito_id": dep, "lote": "L-SC", "vence": _dia(25), "cantidad": 3, "clave_operacion": "sc-entrada"}),
        "deposito entrada")
    limpia(deposito.get(f"/api/vencimientos/productos/{leche}/lotes"), "deposito lotes")
    limpia(deposito.get("/api/productos"), "deposito productos")
    # El encargado (que sí tiene `costos.ver`) marca por la ficha: la respuesta trae `vence` y nada de lo que no es suyo.
    r = escenario["clientes"]["encargado"].put(f"/api/productos/{escenario['sal']}", json={
        "nombre": "Sal fina", "unidad": "u", "precio_venta": "900.00", "precio_costo": "400.00", "codigo": "SAL-1", "vence": True})
    assert r.status_code == 200 and r.json()["vence"] is True


def test_los_vencimientos_estan_libres_en_todos_los_planes(admin_client, escenario):
    """ADR-048: Básico y Premium se distinguen por facturación y multisucursal; no hay `require_module` sobre estas rutas."""
    for modulo in ("facturacion", "multisucursal"):
        admin_client.app.state.modules.set_enabled(modulo, False)
    for ruta in LECTURA:
        assert admin_client.get(ruta.format(p=escenario["leche"])).status_code == 200, ruta
    assert _asignar(admin_client, escenario, "plan-1").status_code == 200
    assert _merma(admin_client, escenario, "plan-2").status_code == 200
    assert admin_client.put(f"/api/vencimientos/productos/{escenario['sal']}", json={"vence": True}).status_code == 200


def test_lo_que_la_pantalla_del_kit_pide_al_abrir_lo_lee_el_deposito(escenario):
    """`libra-ui/comercio/Vencimientos` pide `/api/sucursales` y `/api/productos/categorias` (los filtros; si fallan la pantalla sigue
    sin ellos) y, en «Productos que vencen», `/api/productos` (`catalogo.ver`). El depósito, que no ve costos, recibe los productos sin
    `precio_costo` (`SinCostos`)."""
    deposito = escenario["clientes"]["deposito"]
    sucursales = deposito.get("/api/sucursales")
    assert sucursales.status_code == 200 and all({"id", "nombre"} <= set(s) for s in sucursales.json())
    categorias = deposito.get("/api/productos/categorias")
    assert categorias.status_code == 200 and [c["nombre"] for c in categorias.json()] == ["Almacén"]
    productos = deposito.get("/api/productos")
    assert productos.status_code == 200
    assert {p["nombre"] for p in productos.json()} >= {"Leche 1L", "Sal fina"}
    assert COSTO not in productos.text and "precio_costo" not in productos.text


def test_las_capacidades_llegan_a_la_sesion_de_cada_rol(escenario):
    """`/auth/me` trae las capacidades nuevas (y sólo a quien corresponde): las escribe a mano este test, no las deriva de la matriz."""
    esperado = {
        "admin": {"vencimientos.ver", "vencimientos.marcar", "vencimientos.mover"},
        "encargado": {"vencimientos.ver", "vencimientos.marcar", "vencimientos.mover"},
        "deposito": {"vencimientos.ver", "vencimientos.mover"},
        "vendedor": set(), "cajero": set(), "staff": set(),
    }
    for rol, capacidades in esperado.items():
        recibidas = set(escenario["clientes"][rol].get("/auth/me").json()["capacidades"])
        assert recibidas & {"vencimientos.ver", "vencimientos.marcar", "vencimientos.mover"} == capacidades, rol
