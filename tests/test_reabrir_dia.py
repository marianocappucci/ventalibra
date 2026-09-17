"""Reabrir día (2026-09-17, LibraCore v1.107.0): un admin anula un cierre
diario, con motivo obligatorio, y eso libera la sucursal para volver a abrir
turnos ese día. Ver `app/main.py` (`autorizar_reabrir=Depends(require_admin)`)
y `libracore.caja_router.build_cierre_diario_router`.

Ejercita de paso la migración `0011_reabrir_cierre_diario` de LibraCore: sin
ella no existiría `anulado_en` y `_migrar_libracore()` (conftest) fallaría al
aplicar la cadena, o el `INSERT`/`SELECT` de este módulo reventaría con
"no such column" -- cualquiera de las dos formas pone roja esta suite antes
de llegar a un assert.
"""
from ventas_helpers import caja_default


def _sucursal_principal(client) -> int:
    locs = client.get("/locations").json()
    return next(l["id"] for l in locs if l["is_default"])


def _cerrar_turno_del_dia(client, sucursal_id: int) -> None:
    """Abre y cierra un turno en la sucursal principal, dejando la sucursal
    lista para cerrar el día (sin turnos abiertos)."""
    caja_id = caja_default(client)
    abierto = client.post("/shifts/open", json={"monto_inicial": 0, "caja_id": caja_id})
    assert abierto.status_code == 200, abierto.text
    tid = abierto.json()["turno"]["id"]
    cerrado = client.post(f"/shifts/{tid}/close", json={"monto_declarado": 0, "notas": ""})
    assert cerrado.status_code == 200, cerrado.text


def _cerrar_dia(client, sucursal_id: int) -> dict:
    r = client.post("/api/cierre-diario/cerrar", json={"sucursal_id": sucursal_id, "notas": ""})
    assert r.status_code == 200, r.text
    return r.json()


def test_flujo_completo_reabrir_dia(admin_client, staff_client):
    sucursal_id = _sucursal_principal(admin_client)
    caja_id = caja_default(admin_client)

    _cerrar_turno_del_dia(admin_client, sucursal_id)
    cierre = _cerrar_dia(admin_client, sucursal_id)
    assert cierre["numero"] == 1
    assert cierre["anulado_en"] is None

    # Con el día cerrado, abrir un turno nuevo en esa sucursal da 409 -- el
    # pedido original del humano ("una sucursal con el día cerrado no podía
    # abrir turno").
    bloqueado = admin_client.post("/shifts/open", json={"monto_inicial": 0, "caja_id": caja_id})
    assert bloqueado.status_code == 409, bloqueado.text
    assert "ya está cerrado" in bloqueado.json()["detail"]

    # staff (no admin) no puede reabrir: 403.
    negado = staff_client.post(f"/api/cierre-diario/{cierre['id']}/reabrir", json={"motivo": "prueba"})
    assert negado.status_code == 403, negado.text

    # Motivo vacío: 422, y el cierre sigue activo.
    vacio = admin_client.post(f"/api/cierre-diario/{cierre['id']}/reabrir", json={"motivo": "  "})
    assert vacio.status_code == 422, vacio.text

    # admin, con motivo: 200 y el cierre queda anulado.
    reabierto = admin_client.post(
        f"/api/cierre-diario/{cierre['id']}/reabrir", json={"motivo": "Faltaba abrir turno"}
    )
    assert reabierto.status_code == 200, reabierto.text
    cuerpo = reabierto.json()
    assert cuerpo["anulado_en"] is not None
    assert cuerpo["motivo_anulacion"] == "Faltaba abrir turno"

    # `preview.ya_cerrado` ignora los anulados.
    preview = admin_client.get(f"/api/cierre-diario/preview?sucursal_id={sucursal_id}").json()
    assert preview["ya_cerrado"] is False

    # Reabierto el día, abrir turno ya funciona.
    destrabado = admin_client.post("/shifts/open", json={"monto_inicial": 0, "caja_id": caja_id})
    assert destrabado.status_code == 200, destrabado.text
    tid_destrabado = destrabado.json()["turno"]["id"]
    cerrado = admin_client.post(f"/shifts/{tid_destrabado}/close", json={"monto_declarado": 0, "notas": ""})
    assert cerrado.status_code == 200, cerrado.text

    # Re-cerrar da un número nuevo, y el listado muestra los dos.
    cierre2 = _cerrar_dia(admin_client, sucursal_id)
    assert cierre2["numero"] == 2
    assert cierre2["id"] != cierre["id"]

    listado = admin_client.get(f"/api/cierre-diario?sucursal_id={sucursal_id}").json()
    por_id = {c["id"]: c for c in listado}
    assert por_id[cierre["id"]]["anulado_en"] is not None
    assert por_id[cierre["id"]]["motivo_anulacion"] == "Faltaba abrir turno"
    assert por_id[cierre2["id"]]["anulado_en"] is None


def test_reabrir_cierre_inexistente_da_404(admin_client):
    r = admin_client.post("/api/cierre-diario/999999/reabrir", json={"motivo": "x"})
    assert r.status_code == 404, r.text


def test_reabrir_cierre_ya_anulado_da_409(admin_client):
    sucursal_id = _sucursal_principal(admin_client)
    _cerrar_turno_del_dia(admin_client, sucursal_id)
    cierre = _cerrar_dia(admin_client, sucursal_id)

    primera = admin_client.post(f"/api/cierre-diario/{cierre['id']}/reabrir", json={"motivo": "motivo 1"})
    assert primera.status_code == 200, primera.text

    segunda = admin_client.post(f"/api/cierre-diario/{cierre['id']}/reabrir", json={"motivo": "motivo 2"})
    assert segunda.status_code == 409, segunda.text
