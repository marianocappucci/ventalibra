"""Cajas por sucursal: varios mostradores por sede, con su propio punto de
venta de ARCA, y turno por usuario y por caja (2026-09-16).

Antes de esta feature había una única caja para toda la instancia y el turno
era compartido (`get_turno_activo_any`): con dos locales vendiendo a la vez
eso mezclaba la plata de los dos. Ver `app/services/cajas.py`,
`app/cajas_ganchos.py` (los ganchos de los routers del motor).
"""
from ventas_helpers import (
    abrir_turno,
    caja_default,
    con_stock,
    crear_deposito,
    crear_item,
    crear_sucursal,
    crear_ubicacion,
    hoy,
    registrar_venta,
    sucursal_default,
)


def _crear_sucursal(client, nombre="Sucursal Norte") -> dict:
    """La sucursal (`POST /api/sucursales`): su `id` es el que llevan las cajas; el depósito donde vive su stock es
    `deposito_predeterminado_id`."""
    return crear_sucursal(client, nombre)


def _sembrada(client) -> dict:
    """La sucursal que siembra `app/db.py::connect()` (predeterminada). No es `json()[0]`: el listado va por
    nombre y puede haber más de una."""
    return sucursal_default(client)


def _cajas_de(client, sucursal_id: int) -> list:
    r = client.get(f"/api/cajas?sucursal_id={sucursal_id}")
    assert r.status_code == 200, r.text
    return r.json()


# ── Alta idempotente al arrancar ────────────────────────────────────────────


def test_toda_sucursal_arranca_con_al_menos_una_caja(admin_client):
    """`app/db.py::connect()` siembra un único Location ("Depósito principal")
    en una base nueva; `create_app()` tiene que haberle creado su caja.

    🔴 **No es "Caja 1".** `libracore.db.schema.init_core_schema()` ya siembra
    ella misma una caja default ("Caja Principal", `es_default=1`) cuando la
    tabla `cajas` está vacía -- ANTES de que corra `services/billing.py::
    configure()`, que por eso nunca llega a crear su "Caja VentaLibra" (esa
    rama quedó muerta: `get_default_caja_id()` ya no da `None` para cuando se
    la consulta). Lo que importa acá es que quede UNA sola, marcada default y
    reasignada a la sucursal (no huérfana) -- no de dónde salió el nombre."""
    sucursal = _sembrada(admin_client)
    cajas = _cajas_de(admin_client, sucursal["id"])
    assert len(cajas) == 1
    assert cajas[0]["es_default"]


def test_una_sucursal_nueva_recibe_su_primera_caja_al_crearse(admin_client):
    sucursal = _crear_sucursal(admin_client)
    cajas = _cajas_de(admin_client, sucursal["id"])
    assert len(cajas) == 1
    assert cajas[0]["nombre"] == "Caja 1"
    assert cajas[0]["es_default"]


def test_el_arranque_de_cajas_es_idempotente(tmp_path):
    """Correr `create_app()` dos veces sobre la MISMA base no crea una segunda
    caja por sucursal ni duplica nada."""
    from libracore.db import caja as db_caja
    from motor_de_test import destino_dominio

    from app.main import create_app

    db_path = destino_dominio(tmp_path / "ventalibra.db")
    app1 = create_app(db_path)
    sucursal_id = app1.state.conn.execute(
        "SELECT id FROM locations WHERE is_default = 1 LIMIT 1"
    ).fetchone()[0]
    assert len(db_caja.get_all_cajas(sucursal_id=sucursal_id)) == 1

    app2 = create_app(db_path)
    assert len(db_caja.get_all_cajas(sucursal_id=sucursal_id)) == 1

    app1.state.auth_engine.dispose()
    app2.state.auth_engine.dispose()


# ── ABM ──────────────────────────────────────────────────────────────────


def test_alta_de_caja_con_sucursal_inexistente_da_422(admin_client):
    r = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": 999_999,
    })
    assert r.status_code == 422, r.text


def test_alta_de_caja_con_punto_de_venta_repetido_da_409(admin_client):
    sucursal = _sembrada(admin_client)
    otra = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal["id"], "punto_venta": 7,
    })
    assert otra.status_code == 200, otra.text

    choque = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 3", "sucursal_id": sucursal["id"], "punto_venta": 7,
    })
    assert choque.status_code == 409, choque.text


def test_encargado_no_puede_crear_cajas(encargado_client):
    sucursal = _sembrada(encargado_client)
    r = encargado_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal["id"],
    })
    assert r.status_code == 403, r.text


def test_encargado_puede_listar_cajas(encargado_client):
    r = encargado_client.get("/api/cajas")
    assert r.status_code == 200, r.text


def test_medios_disponibles_lo_sirve_el_motor(admin_client):
    """`GET /api/cajas/medios-disponibles` no choca con `GET /api/cajas/{id}`:
    la ruta la sirve `build_cajas_router` del motor."""
    r = admin_client.get("/api/cajas/medios-disponibles")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
    assert r.json()


def test_editar_caja_no_le_cambia_la_sucursal(admin_client):
    sucursal = _sembrada(admin_client)
    caja = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal["id"],
    }).json()
    editada = admin_client.put(f"/api/cajas/{caja['id']}", json={
        "nombre": "Mostrador 2 (renombrado)", "activo": True,
    })
    assert editada.status_code == 200, editada.text
    assert editada.json()["sucursal_id"] == sucursal["id"]


def test_editar_caja_reemplaza_los_campos_y_el_pos_mp_que_no_viene_se_borra(admin_client):
    """Contrato del motor (el de Contalibra): el PUT guarda la caja tal como llega. Hasta la fase 5 este
    producto conservaba el POS de MercadoPago si el campo se omitía; el kit (`libra-ui/comercio/Cajas`) manda
    siempre todos los campos, así que ya no hace falta y no se diferencia del motor."""
    sucursal = _sembrada(admin_client)
    creada = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador QR", "sucursal_id": sucursal["id"],
        "mp_pos_id": "BIOKOCAJA01",
    })
    assert creada.status_code == 200, creada.text
    caja_id = creada.json()["id"]
    assert creada.json()["mp_pos_id"] == "BIOKOCAJA01"

    conservada = admin_client.put(f"/api/cajas/{caja_id}", json={
        "nombre": "Mostrador QR renombrado", "activo": True, "mp_pos_id": "BIOKOCAJA01",
    })
    assert conservada.status_code == 200, conservada.text
    assert conservada.json()["mp_pos_id"] == "BIOKOCAJA01"
    assert next(c for c in admin_client.get("/api/cajas").json()
                if c["id"] == caja_id)["mp_pos_id"] == "BIOKOCAJA01"

    borrada = admin_client.put(f"/api/cajas/{caja_id}", json={
        "nombre": "Mostrador QR renombrado", "activo": True, "mp_pos_id": None,
    })
    assert borrada.status_code == 200, borrada.text
    assert borrada.json()["mp_pos_id"] is None


def test_pos_mp_invalido_responde_422_al_crear_y_editar(admin_client):
    sucursal = _sembrada(admin_client)
    datos = {"nombre": "Mostrador QR", "sucursal_id": sucursal["id"]}
    invalida = admin_client.post("/api/cajas", json={
        **datos, "mp_pos_id": "BIOKO-CAJA01",
    })
    assert invalida.status_code == 422, invalida.text
    assert "alfanumérico" in invalida.json()["detail"]

    creada = admin_client.post("/api/cajas", json={**datos, "mp_pos_id": "BIOKOCAJA01"})
    assert creada.status_code == 200, creada.text
    caja_id = creada.json()["id"]
    invalida = admin_client.put(f"/api/cajas/{caja_id}", json={
        "nombre": "Mostrador QR", "mp_pos_id": "BIOKO-CAJA01",
    })
    assert invalida.status_code == 422, invalida.text
    assert "alfanumérico" in invalida.json()["detail"]
    assert next(c for c in admin_client.get("/api/cajas").json()
                if c["id"] == caja_id)["mp_pos_id"] == "BIOKOCAJA01"


def test_borrar_caja_con_movimientos_da_422(admin_client):
    item_id = crear_item(admin_client)
    depo = _sembrada(admin_client)["id"]
    con_stock(admin_client, item_id, depo)
    caja_id = caja_default(admin_client)
    abrir_turno(admin_client, caja_id=caja_id)
    registrar_venta(admin_client, item_id)

    r = admin_client.delete(f"/api/cajas/{caja_id}")
    assert r.status_code == 422, r.text


# ── Predeterminada, por sucursal ───────────────────────────────────────────


def test_marcar_predeterminada_es_por_sucursal(admin_client):
    sucursal1 = _sembrada(admin_client)
    caja1_default = _cajas_de(admin_client, sucursal1["id"])[0]

    sucursal2 = _crear_sucursal(admin_client)
    caja2_default = _cajas_de(admin_client, sucursal2["id"])[0]

    # Una segunda caja en la sucursal 1, y se marca predeterminada.
    nueva = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal1["id"],
    }).json()
    r = admin_client.post(f"/api/cajas/{nueva['id']}/set-default")
    assert r.status_code == 200, r.text
    assert bool(r.json()["es_default"]) is True

    # La de la sucursal 1 vieja dejó de serlo...
    vieja = admin_client.get("/api/cajas").json()
    vieja_actual = next(c for c in vieja if c["id"] == caja1_default["id"])
    assert bool(vieja_actual["es_default"]) is False

    # ...pero la predeterminada de la sucursal 2 NO se tocó.
    s2_actual = next(c for c in vieja if c["id"] == caja2_default["id"])
    assert bool(s2_actual["es_default"]) is True


# ── Turno por usuario y por caja ────────────────────────────────────────────


def test_una_caja_no_admite_dos_turnos_abiertos(admin_client, cajero_client):
    caja_id = caja_default(admin_client)
    abrir_turno(admin_client, caja_id=caja_id)

    segundo = cajero_client.post(
        "/api/turnos/abrir", json={"monto_inicial": 0, "caja_id": caja_id}
    )
    assert segundo.status_code == 409, segundo.text
    assert "turno abierto" in segundo.json()["detail"]


def test_abrir_turno_en_caja_inexistente_da_404(admin_client):
    r = admin_client.post("/api/turnos/abrir", json={"monto_inicial": 0, "caja_id": 999_999})
    assert r.status_code == 404, r.text


def test_abrir_turno_en_caja_inactiva_da_422(admin_client):
    sucursal = _sembrada(admin_client)
    caja = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal["id"],
    }).json()
    admin_client.put(f"/api/cajas/{caja['id']}", json={"nombre": caja["nombre"], "activo": False})

    r = admin_client.post("/api/turnos/abrir", json={"monto_inicial": 0, "caja_id": caja["id"]})
    assert r.status_code == 422, r.text


def test_shifts_current_devuelve_caja_y_sucursal(admin_client):
    sucursal = _sembrada(admin_client)
    caja_id = caja_default(admin_client)
    abrir_turno(admin_client, caja_id=caja_id)

    actual = admin_client.get("/api/turnos/actual").json()
    assert actual["turno"]["caja"]["id"] == caja_id
    assert actual["turno"]["sucursal"]["id"] == sucursal["id"]


def test_dos_cajeros_en_dos_sucursales_arquean_por_separado(admin_client, cajero_client):
    """El caso real: dos locales vendiendo a la vez, cada uno con su cajero,
    cada uno con su caja. La venta de cada uno cae en SU turno, no en el del
    otro -- es lo que rompía el turno compartido."""
    sucursal1 = _sembrada(admin_client)
    caja1 = caja_default(admin_client)

    sucursal2 = _crear_sucursal(admin_client)
    caja2 = _cajas_de(admin_client, sucursal2["id"])[0]["id"]

    item_id = crear_item(admin_client)
    # Cada venta sale del depósito de SU sucursal: desde el 2026-09-17 el
    # backend rechaza otro (`app/ganchos.py::validar_deposito`).
    con_stock(admin_client, item_id, sucursal1["id"])
    con_stock(admin_client, item_id, sucursal2["id"])

    tid1 = abrir_turno(admin_client, caja_id=caja1)
    tid2 = abrir_turno(cajero_client, caja_id=caja2)
    assert tid1 != tid2

    registrar_venta(admin_client, item_id, precio="1000.00", cantidad="1",
                    deposito_id=sucursal1["id"])
    registrar_venta(cajero_client, item_id, precio="1000.00", cantidad="3",
                    deposito_id=sucursal2["id"])

    resumen1 = admin_client.get(f"/api/turnos/{tid1}").json()["resumen"]
    resumen2 = cajero_client.get(f"/api/turnos/{tid2}").json()["resumen"]

    assert resumen1["total_ventas"] == 1000.0
    assert resumen2["total_ventas"] == 3000.0


def test_ganchos_turno_para_devuelve_el_del_usuario_que_pide(admin_client, cajero_client):
    """`app/ganchos.py::turno_para` -- desde esta feature ya NO es
    `get_turno_activo_any()` (compartido): tiene que devolver el turno de
    QUIEN está vendiendo, no cualquiera que esté abierto."""
    from libracore.db.core import get_connection

    from app.ganchos import turno_para

    caja_id = caja_default(admin_client)
    sucursal2 = _crear_sucursal(admin_client)
    caja2 = _cajas_de(admin_client, sucursal2["id"])[0]["id"]

    tid_admin = abrir_turno(admin_client, caja_id=caja_id)
    tid_cajero = abrir_turno(cajero_client, caja_id=caja2)

    admin_id = admin_client.get("/auth/me").json()["id"]
    cajero_id = cajero_client.get("/auth/me").json()["id"]

    with get_connection() as conn:
        turno_admin = turno_para(conn, admin_id)
        turno_cajero = turno_para(conn, cajero_id)

    assert turno_admin["id"] == tid_admin
    assert turno_cajero["id"] == tid_cajero
    # Y no al revés: el turno de uno no es el del otro.
    assert turno_admin["id"] != turno_cajero["id"]


def test_turno_para_sin_usuario_da_none(admin_client):
    from libracore.db.core import get_connection

    from app.ganchos import turno_para

    with get_connection() as conn:
        assert turno_para(conn, None) is None


def test_venta_sale_con_el_punto_de_venta_de_la_caja(admin_client):
    """`resolver_punto_venta` (libracore.db.caja): usuario -> turno abierto ->
    caja -> punto de venta. Con turno por caja, la factura sale con el punto
    de venta de la caja donde el cajero está parado."""
    from libracore.db.caja import resolver_punto_venta

    sucursal = _sembrada(admin_client)
    caja = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal["id"], "punto_venta": 5,
    }).json()

    admin_id = admin_client.get("/auth/me").json()["id"]
    abrir_turno(admin_client, caja_id=caja["id"])

    assert resolver_punto_venta(admin_id) == 5


def test_el_movimiento_de_caja_de_la_venta_toma_la_caja_del_turno(admin_client):
    """El ingreso de la venta cae en la caja del TURNO, no en la default.

    `registrar_venta` (libracommerce v0.17.0) llama a
    `create_caja_movimiento(..., turno_id=...)` **sin `caja_id` explícito**:
    hasta libracore #277 eso caía siempre a `get_default_caja_id()`, y en una
    instancia con dos cajas toda venta quedaba anotada en la default aunque
    el cajero estuviera parado en otra -- `get_caja_movimientos` y
    `get_caja_resumen` filtrados por caja mentían (el arqueo y el cierre
    diario no se veían afectados: van por `turnos_caja.caja_id`).

    El fix vive en `libracore.db.caja` y viaja desde v1.105.0; VentaLibra
    está en v1.109.0 (`uv.lock`). Cierra el pendiente "caja_movimientos.
    caja_id cae en la caja default" de wiki/analyses/pendientes-ventalibra.md
    con una medición, no sólo con el pin.
    """
    from libracore.db.core import get_connection

    sucursal = _sembrada(admin_client)
    default = caja_default(admin_client)
    caja = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal["id"],
    }).json()
    # Sin esto el resto del test probaría nada: la caja del turno tiene que
    # ser DISTINTA de la default para que la mutación se note.
    assert caja["id"] != default

    item_id = crear_item(admin_client)
    con_stock(admin_client, item_id, sucursal["id"])
    tid = abrir_turno(admin_client, caja_id=caja["id"])

    registrar_venta(admin_client, item_id, precio="1000.00", cantidad="1")

    with get_connection() as conn:
        filas = conn.execute(
            "SELECT caja_id, turno_id FROM caja_movimientos "
            "WHERE turno_id=? AND tipo='ingreso'",
            (tid,),
        ).fetchall()

    # La venta de un solo pago en efectivo es un único ingreso atado al turno.
    assert len(filas) == 1, f"esperaba 1 movimiento del turno, vinieron {len(filas)}"
    assert filas[0]["turno_id"] == tid
    # 🔴 Con libracore sin #277 esto devuelve la caja DEFAULT y el test muere.
    assert filas[0]["caja_id"] == caja["id"]


# ── Las cajas son de una sucursal, no de un depósito (jerarquía, 2026-09-28) ─


def test_una_base_nueva_nace_con_una_sucursal_con_caja_y_con_deposito(admin_client):
    """`db.connect()` siembra una sucursal predeterminada con su depósito: si no, una instancia nueva no tendría
    ni dónde abrir turno ni de dónde descontar la primera venta."""
    sembrada = _sembrada(admin_client)
    assert len(_cajas_de(admin_client, sembrada["id"])) == 1
    depositos = admin_client.get("/api/depositos").json()
    assert [d["id"] for d in depositos if d["branch_id"] == sembrada["id"]] == [sembrada["deposito_predeterminado_id"]]


def test_un_deposito_nuevo_no_recibe_caja(admin_client):
    sembrada = _sembrada(admin_client)
    crear_deposito(admin_client, "Depósito Norte", sembrada["id"])
    assert len(_cajas_de(admin_client, sembrada["id"])) == 1


def test_no_se_da_de_alta_una_caja_en_una_sucursal_inexistente(admin_client):
    r = admin_client.post("/api/cajas", json={"nombre": "Mostrador", "sucursal_id": 9999})
    assert r.status_code == 422, r.text
    assert "No existe una sucursal activa" in r.json()["detail"]


def test_no_se_da_de_alta_una_caja_en_una_sucursal_dada_de_baja(admin_client):
    sucursal = _crear_sucursal(admin_client)
    baja = admin_client.put(f"/api/sucursales/{sucursal['id']}", json={"nombre": sucursal["nombre"], "activa": False})
    assert baja.status_code == 200, baja.text
    r = admin_client.post("/api/cajas", json={"nombre": "Mostrador", "sucursal_id": sucursal["id"]})
    assert r.status_code == 422, r.text
    assert "No existe una sucursal activa" in r.json()["detail"]


# ── Desactivar una caja (2026-09-26): con movimientos no se puede eliminar ──


def _desactivar(client, caja: dict):
    return client.put(f"/api/cajas/{caja['id']}", json={"nombre": caja["nombre"], "activo": False})


def test_la_unica_caja_activa_de_una_sucursal_no_se_desactiva(admin_client):
    unica = _cajas_de(admin_client, _sembrada(admin_client)["id"])[0]
    r = _desactivar(admin_client, unica)
    assert r.status_code == 409, r.text
    assert "al menos una caja activa" in r.json()["detail"]


def test_no_se_desactiva_una_caja_con_turno_abierto(admin_client):
    sucursal = _sembrada(admin_client)
    admin_client.post("/api/cajas", json={"nombre": "Mostrador 2", "sucursal_id": sucursal["id"]})
    con_turno = _cajas_de(admin_client, sucursal["id"])[0]
    abrir_turno(admin_client, caja_id=con_turno["id"])
    r = _desactivar(admin_client, con_turno)
    assert r.status_code == 409, r.text
    assert "turno abierto" in r.json()["detail"]


def test_al_desactivar_la_predeterminada_pasa_a_otra_activa(admin_client):
    sucursal = _sembrada(admin_client)
    otra = admin_client.post("/api/cajas", json={"nombre": "Mostrador 2", "sucursal_id": sucursal["id"]}).json()
    predeterminada = next(c for c in _cajas_de(admin_client, sucursal["id"]) if c["es_default"])
    r = _desactivar(admin_client, predeterminada)
    assert r.status_code == 200, r.text
    assert bool(r.json()["activo"]) is False and bool(r.json()["es_default"]) is False
    cajas = {c["id"]: c for c in _cajas_de(admin_client, sucursal["id"])}
    assert bool(cajas[otra["id"]]["es_default"]) is True
    assert bool(cajas[otra["id"]]["activo"]) is True


def test_una_caja_sin_sucursal_que_la_resuelva_se_puede_desactivar(admin_client):
    """Una caja histórica cuya `sucursal_id` ya no apunta a ninguna sucursal (dato de antes de la jerarquía, que la
    migración no pudo reasignar) no se puede borrar si tiene movimientos: se desactiva sin la guarda de «al menos
    una activa», porque no hay sucursal a la que dejarle una."""
    from libracore.db import caja as db_caja

    caja_id = db_caja.create_caja_config("Caja vieja", "", [], sucursal_id=9999)
    r = _desactivar(admin_client, {"id": caja_id, "nombre": "Caja vieja"})
    assert r.status_code == 200, r.text
    assert bool(r.json()["activo"]) is False


# ── Fase 5: los routers del motor con los ganchos de VentaLibra (ADR-032) ──────


def test_encargado_tampoco_edita_predetermina_ni_borra_cajas(admin_client, encargado_client):
    """Configurar el local es de admin: lo dice `autorizar_escritura`, no cada ruta."""
    sucursal = _sembrada(admin_client)
    caja = admin_client.post("/api/cajas", json={"nombre": "Otra", "sucursal_id": sucursal["id"]}).json()
    assert encargado_client.put(f"/api/cajas/{caja['id']}", json={"nombre": "X"}).status_code == 403
    assert encargado_client.post(f"/api/cajas/{caja['id']}/set-default").status_code == 403
    assert encargado_client.delete(f"/api/cajas/{caja['id']}").status_code == 403
    assert admin_client.get("/api/cajas").json()  # y el listado sigue siendo de encargado y admin


def test_la_caja_dice_si_tiene_turno_abierto_y_en_que_sucursal_esta(admin_client):
    sucursal = _sembrada(admin_client)
    caja_id = caja_default(admin_client)
    antes = next(c for c in admin_client.get("/api/cajas").json() if c["id"] == caja_id)
    assert antes["tiene_turno_abierto"] is False and antes["sucursal_nombre"] == sucursal["nombre"]
    abrir_turno(admin_client, caja_id=caja_id)
    durante = next(c for c in admin_client.get(f"/api/cajas?sucursal_id={sucursal['id']}").json()
                   if c["id"] == caja_id)
    assert durante["tiene_turno_abierto"] is True


def test_cada_cajero_ve_y_cierra_sus_turnos_y_el_admin_los_de_todos(admin_client, cajero_client):
    """Regla del motor (la de Contalibra): dueño o admin. Hasta la fase 5 cualquier sesión de empleado podía
    cerrar cualquier turno (`/shifts/{id}/close`, sin restricción propia)."""
    sucursal2 = _crear_sucursal(admin_client)
    caja2 = _cajas_de(admin_client, sucursal2["id"])[0]["id"]
    del_admin = abrir_turno(admin_client)
    del_cajero = abrir_turno(cajero_client, caja_id=caja2)

    assert [t["id"] for t in cajero_client.get("/api/turnos").json()["turnos"]] == [del_cajero]
    assert cajero_client.get(f"/api/turnos/{del_admin}").status_code == 403
    assert cajero_client.post(f"/api/turnos/{del_admin}/cerrar", json={"monto_declarado": 0}).status_code == 403
    assert cajero_client.get("/api/turnos/actual").json()["turno"]["id"] == del_cajero
    assert cajero_client.post(f"/api/turnos/{del_cajero}/cerrar", json={"monto_declarado": 0}).status_code == 200
    assert {t["id"] for t in admin_client.get("/api/turnos").json()["turnos"]} == {del_admin, del_cajero}
    assert admin_client.post(f"/api/turnos/{del_admin}/cerrar", json={"monto_declarado": 0}).status_code == 200


def test_el_resumen_del_turno_trae_las_ventas_y_el_arqueo_sin_fiado(admin_client):
    """La pantalla de turnos del kit lee `resumen.ventas`; el arqueo sale de la caja y sin la cuenta
    corriente (fiar no es cobrar)."""
    sucursal = _sembrada(admin_client)
    item_id = crear_item(admin_client)
    con_stock(admin_client, item_id, sucursal["id"])
    tid = abrir_turno(admin_client, monto_inicial=100)
    registrar_venta(admin_client, item_id, precio="1000.00", cantidad="2", deposito_id=sucursal["id"])

    resumen = admin_client.get(f"/api/turnos/{tid}").json()["resumen"]
    assert [v["numero"][:4] for v in resumen["ventas"]] == ["POS-"]
    assert resumen["ventas"][0]["total"] == 2000.0 and resumen["ventas"][0]["estado"] == "cobrada"
    assert resumen["total_ventas"] == 2000.0 and resumen["efectivo_ventas"] == 2000.0
    assert "cuenta_corriente" not in resumen["pagos_por_medio"]


def test_abrir_sin_caja_da_422_y_con_turno_propio_da_409(admin_client):
    assert admin_client.post("/api/turnos/abrir", json={"monto_inicial": 0}).status_code == 422
    tid = abrir_turno(admin_client)
    segundo = admin_client.post("/api/turnos/abrir", json={"monto_inicial": 0, "caja_id": caja_default(admin_client)})
    assert segundo.status_code == 409 and f"#{tid}" in segundo.json()["detail"]
