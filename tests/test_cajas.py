"""Cajas por sucursal: varios mostradores por sede, con su propio punto de
venta de ARCA, y turno por usuario y por caja (2026-09-16).

Antes de esta feature había una única caja para toda la instancia y el turno
era compartido (`get_turno_activo_any`): con dos locales vendiendo a la vez
eso mezclaba la plata de los dos. Ver `app/services/cajas.py`,
`app/routers/cajas.py` y `app/routers/shifts.py`.
"""
from ventas_helpers import abrir_turno, caja_default, con_stock, crear_item, hoy, registrar_venta


def _crear_sucursal(client, nombre="Sucursal Norte") -> dict:
    r = client.post("/locations", json={"name": nombre})
    assert r.status_code == 200, r.text
    return r.json()


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
    sucursal = admin_client.get("/locations").json()[0]
    cajas = _cajas_de(admin_client, sucursal["id"])
    assert len(cajas) == 1
    assert cajas[0]["es_default"] is True


def test_una_sucursal_nueva_recibe_su_primera_caja_al_crearse(admin_client):
    sucursal = _crear_sucursal(admin_client)
    cajas = _cajas_de(admin_client, sucursal["id"])
    assert len(cajas) == 1
    assert cajas[0]["nombre"] == "Caja 1"
    assert cajas[0]["es_default"] is True


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
    sucursal = admin_client.get("/locations").json()[0]
    otra = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal["id"], "punto_venta": 7,
    })
    assert otra.status_code == 201, otra.text

    choque = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 3", "sucursal_id": sucursal["id"], "punto_venta": 7,
    })
    assert choque.status_code == 409, choque.text


def test_staff_no_puede_crear_cajas(staff_client):
    sucursal = staff_client.get("/locations").json()[0]
    r = staff_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal["id"],
    })
    assert r.status_code == 403, r.text


def test_staff_puede_listar_cajas(staff_client):
    r = staff_client.get("/api/cajas")
    assert r.status_code == 200, r.text


def test_medios_disponibles_sigue_sirviendola_medios_py(admin_client):
    """`GET /api/cajas/medios-disponibles` no choca con `GET /api/cajas/{id}`:
    la ruta la sigue sirviendo `app/routers/medios.py`."""
    r = admin_client.get("/api/cajas/medios-disponibles")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
    assert r.json()


def test_editar_caja_no_le_cambia_la_sucursal(admin_client):
    sucursal = admin_client.get("/locations").json()[0]
    caja = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal["id"],
    }).json()
    editada = admin_client.put(f"/api/cajas/{caja['id']}", json={
        "nombre": "Mostrador 2 (renombrado)", "activo": True,
    })
    assert editada.status_code == 200, editada.text
    assert editada.json()["sucursal_id"] == sucursal["id"]


def test_borrar_caja_con_movimientos_da_422(admin_client):
    item_id = crear_item(admin_client)
    depo = admin_client.get("/locations").json()[0]["id"]
    con_stock(admin_client, item_id, depo)
    caja_id = caja_default(admin_client)
    abrir_turno(admin_client, caja_id=caja_id)
    registrar_venta(admin_client, item_id)

    r = admin_client.delete(f"/api/cajas/{caja_id}")
    assert r.status_code == 422, r.text


# ── Predeterminada, por sucursal ───────────────────────────────────────────


def test_marcar_predeterminada_es_por_sucursal(admin_client):
    sucursal1 = admin_client.get("/locations").json()[0]
    caja1_default = _cajas_de(admin_client, sucursal1["id"])[0]

    sucursal2 = _crear_sucursal(admin_client)
    caja2_default = _cajas_de(admin_client, sucursal2["id"])[0]

    # Una segunda caja en la sucursal 1, y se marca predeterminada.
    nueva = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal1["id"],
    }).json()
    r = admin_client.post(f"/api/cajas/{nueva['id']}/predeterminada")
    assert r.status_code == 200, r.text
    assert r.json()["es_default"] is True

    # La de la sucursal 1 vieja dejó de serlo...
    vieja = admin_client.get("/api/cajas").json()
    vieja_actual = next(c for c in vieja if c["id"] == caja1_default["id"])
    assert vieja_actual["es_default"] is False

    # ...pero la predeterminada de la sucursal 2 NO se tocó.
    s2_actual = next(c for c in vieja if c["id"] == caja2_default["id"])
    assert s2_actual["es_default"] is True


# ── Turno por usuario y por caja ────────────────────────────────────────────


def test_una_caja_no_admite_dos_turnos_abiertos(admin_client, staff_client):
    caja_id = caja_default(admin_client)
    abrir_turno(admin_client, caja_id=caja_id)

    segundo = staff_client.post(
        "/shifts/open", json={"monto_inicial": 0, "caja_id": caja_id}
    )
    assert segundo.status_code == 409, segundo.text
    assert "turno abierto" in segundo.json()["detail"]


def test_abrir_turno_en_caja_inexistente_da_404(admin_client):
    r = admin_client.post("/shifts/open", json={"monto_inicial": 0, "caja_id": 999_999})
    assert r.status_code == 404, r.text


def test_abrir_turno_en_caja_inactiva_da_422(admin_client):
    sucursal = admin_client.get("/locations").json()[0]
    caja = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal["id"],
    }).json()
    admin_client.put(f"/api/cajas/{caja['id']}", json={"nombre": caja["nombre"], "activo": False})

    r = admin_client.post("/shifts/open", json={"monto_inicial": 0, "caja_id": caja["id"]})
    assert r.status_code == 422, r.text


def test_shifts_current_devuelve_caja_y_sucursal(admin_client):
    sucursal = admin_client.get("/locations").json()[0]
    caja_id = caja_default(admin_client)
    abrir_turno(admin_client, caja_id=caja_id)

    actual = admin_client.get("/shifts/current").json()
    assert actual["turno"]["caja"]["id"] == caja_id
    assert actual["turno"]["sucursal"]["id"] == sucursal["id"]


def test_dos_cajeros_en_dos_sucursales_arquean_por_separado(admin_client, staff_client):
    """El caso real: dos locales vendiendo a la vez, cada uno con su cajero,
    cada uno con su caja. La venta de cada uno cae en SU turno, no en el del
    otro -- es lo que rompía el turno compartido."""
    sucursal1 = admin_client.get("/locations").json()[0]
    caja1 = caja_default(admin_client)

    sucursal2 = _crear_sucursal(admin_client)
    caja2 = _cajas_de(admin_client, sucursal2["id"])[0]["id"]

    item_id = crear_item(admin_client)
    # Cada venta sale del depósito de SU sucursal: desde el 2026-09-17 el
    # backend rechaza otro (`app/ganchos.py::validar_deposito`).
    con_stock(admin_client, item_id, sucursal1["id"])
    con_stock(admin_client, item_id, sucursal2["id"])

    tid1 = abrir_turno(admin_client, caja_id=caja1)
    tid2 = abrir_turno(staff_client, caja_id=caja2)
    assert tid1 != tid2

    registrar_venta(admin_client, item_id, precio="1000.00", cantidad="1",
                    deposito_id=sucursal1["id"])
    registrar_venta(staff_client, item_id, precio="1000.00", cantidad="3",
                    deposito_id=sucursal2["id"])

    resumen1 = admin_client.get(f"/shifts/{tid1}/summary").json()["resumen"]
    resumen2 = staff_client.get(f"/shifts/{tid2}/summary").json()["resumen"]

    assert resumen1["total_ventas"] == 1000.0
    assert resumen2["total_ventas"] == 3000.0


def test_ganchos_turno_para_devuelve_el_del_usuario_que_pide(admin_client, staff_client):
    """`app/ganchos.py::turno_para` -- desde esta feature ya NO es
    `get_turno_activo_any()` (compartido): tiene que devolver el turno de
    QUIEN está vendiendo, no cualquiera que esté abierto."""
    from libracore.db.core import get_connection

    from app.ganchos import turno_para

    caja_id = caja_default(admin_client)
    sucursal2 = _crear_sucursal(admin_client)
    caja2 = _cajas_de(admin_client, sucursal2["id"])[0]["id"]

    tid_admin = abrir_turno(admin_client, caja_id=caja_id)
    tid_staff = abrir_turno(staff_client, caja_id=caja2)

    admin_id = admin_client.get("/auth/me").json()["id"]
    staff_id = staff_client.get("/auth/me").json()["id"]

    with get_connection() as conn:
        turno_admin = turno_para(conn, admin_id)
        turno_staff = turno_para(conn, staff_id)

    assert turno_admin["id"] == tid_admin
    assert turno_staff["id"] == tid_staff
    # Y no al revés: el turno de uno no es el del otro.
    assert turno_admin["id"] != turno_staff["id"]


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

    sucursal = admin_client.get("/locations").json()[0]
    caja = admin_client.post("/api/cajas", json={
        "nombre": "Mostrador 2", "sucursal_id": sucursal["id"], "punto_venta": 5,
    }).json()

    admin_id = admin_client.get("/auth/me").json()["id"]
    abrir_turno(admin_client, caja_id=caja["id"])

    assert resolver_punto_venta(admin_id) == 5
