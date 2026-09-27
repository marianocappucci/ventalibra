"""Sucursales y depósitos con el router del motor (`/api/depositos`, fase 6, ADR-033).

Hasta la fase 6 esto era `/locations` (`app/routers/locations.py`). Ahora es `libracommerce.web.catalogo_router.
build_depositos_router`, el mismo de Contalibra y Restolibra, con las reglas de VentaLibra como ganchos
(`app/depositos_ganchos.py`): dos tipos que no se cambian, como mínimo una sucursal y un depósito activos, la
sucursal con turno abierto no se desactiva, una sucursal no se elimina, y la sucursal nueva recibe su caja.

Las guardas de «a lo sumo un default» y «no desactivar el default» son del motor
(`libracommerce.erp.catalogo.update_deposito`/`set_default_deposito`).
"""
from conftest import https_client
from motor_de_test import destino_dominio
from test_cajas import _cajas_de, _crear_sucursal
from ventas_helpers import abrir_turno, con_stock, crear_item, crear_ubicacion

from app.main import create_app


def _sucursal_default(client) -> dict:
    return next(loc for loc in client.get("/api/depositos").json() if loc["es_default"])


def _editar(client, loc: dict, **cambios):
    cuerpo = {"nombre": loc["nombre"], "descripcion": loc["descripcion"] or "", "activo": True} | cambios
    return client.put(f"/api/depositos/{loc['id']}", json=cuerpo)


def test_editar_sucursal_cambia_el_nombre(admin_client):
    sucursal = _crear_sucursal(admin_client, "Sucursal Norte")

    editada = _editar(admin_client, sucursal, nombre="  Sucursal Norte (renombrada)  ")

    assert editada.status_code == 200, editada.text
    # El nombre se guarda sin los espacios del padding -- mismo criterio que el resto de la familia.
    assert editada.json()["nombre"] == "Sucursal Norte (renombrada)"
    assert editada.json()["tipo"] == "store"


def test_marcar_default_desmarca_la_anterior(admin_client):
    """`set-default` en la sucursal nueva deja EXACTAMENTE una default."""
    vieja_default = _sucursal_default(admin_client)
    nueva = _crear_sucursal(admin_client, "Sucursal Sur")

    r = admin_client.post(f"/api/depositos/{nueva['id']}/set-default")
    assert r.status_code == 200, r.text
    assert r.json()["es_default"]

    depositos = admin_client.get("/api/depositos").json()
    assert [d["id"] for d in depositos if d["es_default"]] == [nueva["id"]]
    assert not next(d for d in depositos if d["id"] == vieja_default["id"])["es_default"]


def test_no_se_marca_default_una_inactiva_ni_se_escribe(admin_client):
    """Guarda del motor: una default inactiva le seguiría cargando stock en silencio a un depósito dado de baja."""
    otra = _crear_sucursal(admin_client, "Sucursal Norte")
    assert _editar(admin_client, otra, activo=False).status_code == 200

    r = admin_client.post(f"/api/depositos/{otra['id']}/set-default")
    assert r.status_code == 422, r.text
    assert "inactivo" in r.json()["detail"]
    assert _sucursal_default(admin_client)["id"] != otra["id"]


def test_desactivar_la_sucursal_default_da_422_y_no_deja_nada_a_medias(admin_client):
    _crear_sucursal(admin_client, "Otra sucursal")  # así no es la última: la frena la guarda del motor
    default = _sucursal_default(admin_client)

    r = _editar(admin_client, default, activo=False)

    assert r.status_code == 422, r.text
    assert "por defecto" in r.json()["detail"]
    assert _sucursal_default(admin_client)["activo"]  # sigue activa


def test_desactivar_sucursal_con_turno_abierto_da_409(admin_client):
    sucursal = _crear_sucursal(admin_client, "Sucursal con turno")
    caja_id = _cajas_de(admin_client, sucursal["id"])[0]["id"]
    abrir_turno(admin_client, caja_id=caja_id)

    r = _editar(admin_client, sucursal, activo=False)

    assert r.status_code == 409, r.text
    assert "turno" in r.json()["detail"]
    assert next(d for d in admin_client.get("/api/depositos").json() if d["id"] == sucursal["id"])["activo"]


def test_desactivar_sucursal_sin_turno_abierto_funciona(admin_client):
    """Control positivo del test anterior: la guarda es por turno abierto, no por editar en general."""
    sucursal = _crear_sucursal(admin_client, "Sucursal sin ventas")

    r = _editar(admin_client, sucursal, activo=False)

    assert r.status_code == 200, r.text
    assert not r.json()["activo"]
    # El listado del motor trae también las inactivas (la pantalla las muestra apagadas y permite reactivarlas).
    assert not next(d for d in admin_client.get("/api/depositos").json() if d["id"] == sucursal["id"])["activo"]


def test_editar_inexistente_da_404(admin_client):
    r = admin_client.put("/api/depositos/999999", json={"nombre": "x", "activo": True})
    assert r.status_code == 404, r.text


def test_editar_con_nombre_vacio_da_422(admin_client):
    sucursal = _sucursal_default(admin_client)
    r = admin_client.put(f"/api/depositos/{sucursal['id']}", json={"nombre": "   ", "activo": True})
    assert r.status_code == 422, r.text


def test_editar_sin_sesion_da_401(tmp_path):
    with https_client(create_app(destino_dominio(tmp_path / "ventalibra.db"))) as sin_sesion:
        r = sin_sesion.put("/api/depositos/1", json={"nombre": "x", "activo": True})
        assert r.status_code == 401, r.text


def test_el_cajero_no_crea_edita_predetermina_ni_borra_pero_las_lista(admin_client, staff_client):
    """Alta, edición, predeterminada y baja, sólo admin (decisión del humano, 2026-09-17). El listado sigue abierto: el
    POS lo necesita para abrir turno."""
    sucursal = _crear_sucursal(admin_client, "Sucursal del admin")

    assert staff_client.post("/api/depositos", json={"nombre": "Del cajero"}).status_code == 403
    assert staff_client.put(
        f"/api/depositos/{sucursal['id']}", json={"nombre": "Renombrada", "activo": True}
    ).status_code == 403
    assert staff_client.post(f"/api/depositos/{sucursal['id']}/set-default").status_code == 403
    assert staff_client.delete(f"/api/depositos/{sucursal['id']}").status_code == 403

    assert staff_client.get("/api/depositos").status_code == 200
    nombres = {d["nombre"] for d in admin_client.get("/api/depositos").json()}
    assert "Del cajero" not in nombres and "Sucursal del admin" in nombres


def test_el_cambio_de_default_lo_ve_otra_conexion(admin_client):
    """🔴 Un default que sólo ve la conexión de la app y no la de cada venta rechaza toda venta con 422. Se lee ACÁ
    por una conexión distinta, que es lo que hace una venta."""
    import psycopg
    from motor_de_test import TEST_DATABASE_URL

    nueva = _crear_sucursal(admin_client, "Sucursal Nueva")
    r = admin_client.post(f"/api/depositos/{nueva['id']}/set-default")
    assert r.status_code == 200, r.text
    with psycopg.connect(TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)) as otra:
        defaults = otra.execute("SELECT id FROM locations WHERE is_default = 1").fetchall()
    assert defaults == [(nueva["id"],)]


# ── Dos tipos, y como mínimo uno de cada uno (decisión del humano, 2026-09-25) ──


def _tipos_activos(client) -> list[str]:
    return sorted(d["tipo"] for d in client.get("/api/depositos").json() if d["activo"])


def test_una_base_nueva_declara_una_sucursal_y_un_deposito(admin_client):
    assert _tipos_activos(admin_client) == ["store", "warehouse"]


def test_el_tipo_se_elige_entre_sucursal_y_deposito(admin_client):
    r = admin_client.post("/api/depositos", json={"nombre": "Local", "tipo": "Negocio"})
    assert r.status_code == 422, r.text
    # Sin tipo, un depósito, como siempre.
    r = admin_client.post("/api/depositos", json={"nombre": "Sin tipo"})
    assert r.status_code == 200 and r.json()["tipo"] == "warehouse"


def test_no_se_deja_a_la_instancia_sin_su_unica_sucursal_o_deposito(admin_client):
    deposito = next(d for d in admin_client.get("/api/depositos").json() if d["tipo"] == "warehouse")
    assert not deposito["es_default"]  # el default es la sucursal sembrada

    r = _editar(admin_client, deposito, activo=False)
    assert r.status_code == 409, r.text
    assert "como mínimo" in r.json()["detail"]
    assert _tipos_activos(admin_client) == ["store", "warehouse"]


def test_el_tipo_no_se_cambia_al_editar(admin_client):
    """Una sucursal sigue siendo sucursal y un depósito, depósito (decisión del humano, 2026-09-26): el tipo se elige
    al crear, y el `PUT` del motor ni lo recibe."""
    depositos = admin_client.get("/api/depositos").json()
    sucursal = next(d for d in depositos if d["tipo"] == "store")
    deposito = next(d for d in depositos if d["tipo"] == "warehouse")
    for loc, intento in ((sucursal, "warehouse"), (deposito, "store")):
        r = _editar(admin_client, loc, tipo=intento)  # el campo no existe en el payload: se ignora
        assert r.status_code == 200, r.text
        assert r.json()["tipo"] == loc["tipo"]
    assert _tipos_activos(admin_client) == ["store", "warehouse"]


def test_con_otro_deposito_se_puede_dar_de_baja_el_primero(admin_client):
    deposito = next(d for d in admin_client.get("/api/depositos").json() if d["tipo"] == "warehouse")
    crear_ubicacion(admin_client, "Depósito 2", "warehouse")
    assert _editar(admin_client, deposito, activo=False).status_code == 200


def test_el_arranque_completa_el_tipo_que_falta_y_es_idempotente(admin_client):
    from app.services.locations import LocationService

    conn = admin_client.app.state.conn
    conn.execute("DELETE FROM locations WHERE location_type = 'warehouse'")
    conn.commit()
    servicio = LocationService(conn)
    assert servicio.asegurar_tipos_minimos() == ["Depósito 1"]
    assert servicio.asegurar_tipos_minimos() == []
    assert _tipos_activos(admin_client) == ["store", "warehouse"]


# ── Alta y baja (fase 6) ────────────────────────────────────────────────────


def test_la_sucursal_nueva_recibe_su_caja_y_el_deposito_no(admin_client):
    sucursal = crear_ubicacion(admin_client, "Sucursal Este", "store")
    deposito = crear_ubicacion(admin_client, "Depósito Este", "warehouse")
    assert len(_cajas_de(admin_client, sucursal["id"])) == 1
    assert _cajas_de(admin_client, deposito["id"]) == []


def test_una_sucursal_no_se_elimina_se_desactiva(admin_client):
    sucursal = crear_ubicacion(admin_client, "Sucursal Oeste", "store")
    r = admin_client.delete(f"/api/depositos/{sucursal['id']}")
    assert r.status_code == 409, r.text
    assert "desactivala" in r.json()["detail"]
    assert sucursal["id"] in [d["id"] for d in admin_client.get("/api/depositos").json()]


def test_un_deposito_sin_movimientos_se_elimina_y_con_movimientos_no(admin_client):
    vacio = crear_ubicacion(admin_client, "Depósito vacío", "warehouse")
    con_mov = crear_ubicacion(admin_client, "Depósito con stock", "warehouse")
    con_stock(admin_client, crear_item(admin_client), con_mov["id"], "3")

    assert admin_client.delete(f"/api/depositos/{vacio['id']}").json() == {"ok": True}
    r = admin_client.delete(f"/api/depositos/{con_mov['id']}")
    assert r.status_code == 422, r.text
    assert "movimientos" in r.json()["detail"]


def test_no_se_elimina_el_ultimo_deposito_activo(admin_client):
    deposito = next(d for d in admin_client.get("/api/depositos").json() if d["tipo"] == "warehouse")
    r = admin_client.delete(f"/api/depositos/{deposito['id']}")
    assert r.status_code == 409, r.text
    assert "como mínimo" in r.json()["detail"]


# ── Los routers propios se retiraron ──


def test_las_rutas_viejas_ya_no_existen(admin_client):
    for metodo, ruta in (("get", "/locations"), ("post", "/locations"), ("post", "/stock/adjustments"),
                         ("post", "/stock/transferir"), ("get", "/stock/por-deposito/grilla"),
                         ("get", "/stock/transferencias/historial")):
        r = getattr(admin_client, metodo)(ruta)
        assert r.status_code in (404, 405), f"{metodo.upper()} {ruta} -> {r.status_code}"
