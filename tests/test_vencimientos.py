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

🔴 **Lo que este archivo fija y va a cambiar en A-4 (FEFO en ventas):**
- Hoy una venta de un producto marcado descuenta del stock «sin lote», no de un lote
  (`test_hasta_a4_una_venta_de_un_producto_marcado_descuenta_del_sin_lote`). Cuando las ventas descuenten por lote, ese test tiene que
  cambiar a propósito.
- 🔴 **La baja de un lote (`POST /api/vencimientos/merma`) está DESHABILITADA hasta A-4** (`app/vencimientos_guarda.py`, ADR-052): 409 para
  todos los roles, admin incluido. Los tests de ese 409 están juntos en el bloque «Deshabilitada hasta A-4» y se saltean solos si se
  pone `MERMA_DESHABILITADA = False`. El resto del flujo de merma del motor (saldo, idempotencia, `created_by`, costos, plan) sigue
  probado con la fixture `merma_habilitada`, que apaga esa dependencia. **Reactivarla:** quitar la dependencia de `app/main.py`,
  poner `MERMA_DESHABILITADA = False` (o borrar el bloque y la fixture) y listo.
"""
import re
from datetime import date, timedelta

import pytest
from conftest import https_client
from motor_de_test import destino_dominio
from ventas_helpers import abrir_turno, deposito_default, hoy, registrar_venta

from app import permisos
from app.costos import extras_de
from app.main import create_app
from app.vencimientos_guarda import MENSAJE, merma_deshabilitada

#: Costos que ninguna otra cifra del escenario repite: si aparecen en una respuesta, se filtraron.
COSTO = "731.42"
COSTO_DE_LA_RECEPCION = "543.21"

#: 🔴 El ÚNICO lugar donde se reactivan los tests de la baja de un lote: `True` mientras `app/main.py` ponga `merma_deshabilitada` (hasta A-4).
MERMA_DESHABILITADA = True

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


@pytest.fixture
def merma_habilitada(admin_client):
    """La baja de un lote funcionando: apaga `merma_deshabilitada` (ADR-052) para seguir probando el camino del motor (saldo, idempotencia,
    `created_by`). Con la dependencia ya retirada de `app/main.py` (A-4) es un no-op."""
    admin_client.app.dependency_overrides[merma_deshabilitada] = lambda: None
    yield
    admin_client.app.dependency_overrides.pop(merma_deshabilitada, None)


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
    assert [tuple(v) for v in conn.execute("SELECT version_num FROM alembic_version_libracommerce").fetchall()] == [
        ("0002_vencimientos_lotes",)]


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


def test_dar_de_baja_un_lote_vencido_es_una_merma_a_nombre_de_quien_la_hizo_con_la_baja_habilitada(mueve, escenario, merma_habilitada):
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


def test_un_reintento_con_la_misma_clave_no_vuelve_a_escribir(mueve, escenario, merma_habilitada):
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


def test_cuerpos_invalidos_son_422_y_no_escriben(admin_client, escenario, merma_habilitada):
    antes = _movimientos(admin_client, escenario["leche"])
    assert _asignar(admin_client, escenario, "").status_code == 422  # la clave es obligatoria
    assert _asignar(admin_client, escenario, "k", cantidad=0).status_code == 422
    assert _asignar(admin_client, escenario, "k", deposito_id=999999).status_code == 422
    assert _merma(admin_client, escenario, "k", cantidad=-1).status_code == 422
    assert admin_client.put(f"/api/vencimientos/productos/{escenario['leche']}", json={"vence": "si"}).status_code == 422
    assert admin_client.put("/api/vencimientos/productos/999999", json={"vence": True}).status_code == 404
    assert _movimientos(admin_client, escenario["leche"]) == antes


# ── Deshabilitada hasta A-4: la baja de un lote (ADR-052) ────────────────────
#
# 🔴 Todo este bloque se saltea solo con `MERMA_DESHABILITADA = False`. El flujo de la merma del motor sigue probado más arriba con
# `merma_habilitada`.

deshabilitada = pytest.mark.skipif(not MERMA_DESHABILITADA, reason="la baja de un lote ya está habilitada (A-4)")


@deshabilitada
def test_la_baja_de_un_lote_es_409_para_admin_encargado_y_deposito_y_no_toca_el_ledger(mueve, escenario):
    antes = _movimientos(mueve, escenario["leche"])
    for cuerpo in ({}, {"cantidad": 1, "clave_operacion": "otra"}, {"lote": "no-existe"}):
        r = _merma(mueve, escenario, "rechazada-1", **cuerpo)
        assert r.status_code == 409 and r.json()["detail"] == MENSAJE, r.text
    # Ni con un cuerpo que ni siquiera es un objeto: la dependencia corre antes de validar el cuerpo y no llega al motor.
    r = mueve.post("/api/vencimientos/merma", content=b"[]", headers={"content-type": "application/json"})
    assert r.status_code == 409 and r.json()["detail"] == MENSAJE
    assert "ajuste de stock" in MENSAJE and "descontaría dos veces" in MENSAJE
    assert _movimientos(mueve, escenario["leche"]) == antes
    assert {f["lote"]: f["saldo"] for f in _reporte(mueve, dias=90)["lotes"]} == {"L-VENCIDO": 4, "L-PRONTO": 10, "L-LEJANO": 6}


@deshabilitada
def test_el_resto_recibe_el_mismo_rechazo_de_siempre_y_asignar_sigue_andando(escenario):
    """El permiso corre ANTES que el 409: el mostrador sigue con 403 y el anónimo con 401. Y la asignación, que conserva el total, no
    cambia: 200 para los tres roles que pueden, en la misma ruta de escritura."""
    for rol in ROLES_SIN_ACCESO:
        r = _merma(escenario["clientes"][rol], escenario, f"sin-permiso-{rol}")
        assert r.status_code == 403 and r.json()["detail"] == "forbidden", (rol, r.text)
    assert _merma(https_client(escenario["clientes"]["admin"].app), escenario, "anonimo").status_code == 401
    for i, rol in enumerate(("admin", "encargado", "deposito")):
        r = _asignar(escenario["clientes"][rol], escenario, f"asignar-sigue-{i}", cantidad=1)
        assert r.status_code == 200 and r.json()["repetida"] is False, (rol, r.text)
        assert _merma(escenario["clientes"][rol], escenario, f"merma-sigue-{i}").status_code == 409


# ── Hasta A-4: las ventas no saben de lotes ──────────────────────────────────


def test_un_producto_sin_marcar_no_cambia_nada_en_el_ledger_de_una_venta(admin_client, escenario):
    """La Sal no está marcada: su venta escribe el movimiento de siempre, sin lote ni vencimiento, y no aparece en ningún reporte.
    (No se tocó el camino de ventas: lo que se prueba es que el motor nuevo no lo cambia.)"""
    abrir_turno(admin_client)
    antes = _movimientos(admin_client, escenario["sal"])
    registrar_venta(admin_client, escenario["sal"], precio="900.00", cantidad="2")
    (venta,) = _movimientos(admin_client, escenario["sal"])[len(antes):]
    assert (float(venta[2]), venta[3], venta[4]) == (-2.0, None, None)
    assert venta[0] != "waste"
    assert all(f["producto_id"] != escenario["sal"] for f in _reporte(admin_client, dias=365)["lotes"] + _reporte(admin_client)["sin_lote"])


def test_hasta_a4_una_venta_de_un_producto_marcado_descuenta_del_sin_lote(admin_client, escenario):
    """🔴 La LIMITACIÓN de ADR-052, medida: en un producto marcado la venta resta del bucket «sin lote» y no del lote del que salió la
    mercadería, así que el saldo por lote sobreestima. Cuando A-4 (FEFO) descuente por lote este test tiene que cambiar."""
    abrir_turno(admin_client)
    registrar_venta(admin_client, escenario["leche"], precio="1500.00", cantidad="10")
    m = _reporte(admin_client)
    assert {f["lote"]: f["saldo"] for f in m["lotes"]} == {"L-VENCIDO": 4, "L-PRONTO": 10}  # los lotes siguen enteros
    (sin,) = m["sin_lote"]
    assert (sin["saldo"], sin["situacion"]) == (-2, "salidas_sin_lote")  # 8 - 10: el negativo que avisa la pantalla


# ── Sin costos, sin gate de plan, y lo que pide la pantalla ──────────────────


def test_ningun_endpoint_de_vencimientos_revela_costos(escenario, merma_habilitada):
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


def test_los_vencimientos_estan_libres_en_todos_los_planes(admin_client, escenario, merma_habilitada):
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


def test_la_guarda_de_la_merma_no_se_salta_con_un_prefijo_asgi():
    """Hallazgo de Codex: bajo un `root_path` Starlette lo descarta para elegir el endpoint pero `request.url.path` lo conserva;
    la guarda tiene que mirar también la ruta resuelta (y nunca dejar pasar la merma)."""
    from types import SimpleNamespace

    from fastapi import HTTPException
    from starlette.requests import Request

    def pedido(metodo, url, ruta_resuelta):
        return Request({"type": "http", "method": metodo, "path": url, "root_path": "/venta", "headers": [],
                        "query_string": b"", "route": SimpleNamespace(path=ruta_resuelta)})

    for url in ("/venta/api/vencimientos/merma", "/venta/api/vencimientos/merma/", "/api/vencimientos/merma"):
        with pytest.raises(HTTPException) as e:
            merma_deshabilitada(pedido("POST", url, "/api/vencimientos/merma"))
        assert e.value.status_code == 409
    # La URL pedida engaña pero el router resolvió la merma: también se bloquea.
    with pytest.raises(HTTPException):
        merma_deshabilitada(pedido("POST", "/otra/cosa", "/api/vencimientos/merma"))
    # Asignar, lecturas y otros métodos pasan.
    merma_deshabilitada(pedido("POST", "/venta/api/vencimientos/asignar", "/api/vencimientos/asignar"))
    merma_deshabilitada(pedido("GET", "/venta/api/vencimientos", "/api/vencimientos"))
    merma_deshabilitada(pedido("PUT", "/venta/api/vencimientos/productos/1", "/api/vencimientos/productos/{producto_id}"))
