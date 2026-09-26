"""Edición de sucursales (`PUT /locations/{id}`).

Hasta esta feature (2026-09-17) una sucursal se podía crear pero no editar, y
no había forma de elegir sobre cuál trabajar -- eso último se resuelve en el
POS, al abrir turno (ver `frontend/src/test/pos-turno-por-caja.test.tsx`).

Las guardas de "a lo sumo un default" y "no desactivar el default" son del
motor (`libracommerce.erp.catalogo.update_deposito`/`set_default_deposito`,
v0.17.0) -- `app/services/locations.py::LocationService.update` las usa en vez
de reimplementarlas. Lo único propio de acá es el 409 por turno abierto.
"""
from conftest import https_client
from motor_de_test import destino_dominio
from test_cajas import _cajas_de, _crear_sucursal
from ventas_helpers import abrir_turno

from app.main import create_app


def _sucursal_default(client) -> dict:
    locations = client.get("/locations").json()
    return next(loc for loc in locations if loc["is_default"])


def test_editar_sucursal_cambia_nombre_y_tipo(admin_client):
    sucursal = _crear_sucursal(admin_client, "Sucursal Norte")

    editada = admin_client.put(f"/locations/{sucursal['id']}", json={
        "name": "  Sucursal Norte (renombrada)  ",
        "location_type": "store",
        "is_default": sucursal["is_default"],
        "active": sucursal["active"],
    })

    assert editada.status_code == 200, editada.text
    cuerpo = editada.json()
    # El nombre se guarda sin los espacios del padding -- mismo criterio que
    # el resto de la familia (`.strip()` antes de persistir).
    assert cuerpo["name"] == "Sucursal Norte (renombrada)"
    assert cuerpo["location_type"] == "store"


def test_marcar_default_desmarca_la_anterior(admin_client):
    """`is_default=true` en la sucursal nueva deja EXACTAMENTE una default."""
    vieja_default = _sucursal_default(admin_client)
    nueva = _crear_sucursal(admin_client, "Sucursal Sur")

    r = admin_client.put(f"/locations/{nueva['id']}", json={
        "name": nueva["name"], "location_type": nueva["location_type"],
        "is_default": True, "active": True,
    })
    assert r.status_code == 200, r.text
    assert r.json()["is_default"] is True

    locations = admin_client.get("/locations").json()
    defaults = [loc for loc in locations if loc["is_default"]]
    assert [loc["id"] for loc in defaults] == [nueva["id"]]
    assert next(loc for loc in locations if loc["id"] == vieja_default["id"])["is_default"] is False


def test_desmarcar_la_default_da_409_y_no_la_deja_sin_default(admin_client):
    """`is_default=false` sobre la default dejaría la instancia SIN ninguna: el
    motor caería al `ORDER BY id LIMIT 1` de `get_default_deposito_id`, que no
    mira `active` (pendiente B.4 de libracommerce) y es lo que usa
    `ganchos.validar_deposito` cuando la venta no trae depósito. La default se
    cambia marcando OTRA."""
    default = _sucursal_default(admin_client)

    r = admin_client.put(f"/locations/{default['id']}", json={
        "name": default["name"], "location_type": default["location_type"],
        "is_default": False, "active": True,
    })
    assert r.status_code == 409, r.text
    assert "marcá otra" in r.json()["detail"]
    assert _sucursal_default(admin_client)["id"] == default["id"]


def test_marcar_default_una_inactiva_en_el_mismo_pedido_da_409_sin_escribir(admin_client):
    """`active=false` + `is_default=true` sobre una no-default: antes se
    desactivaba primero y recién después `set_default_deposito` rechazaba,
    dejando la desactivación escrita a pesar del 409."""
    otra = admin_client.post("/locations", json={"name": "Sucursal Norte", "location_type": "store"}).json()

    r = admin_client.put(f"/locations/{otra['id']}", json={
        "name": otra["name"], "location_type": otra["location_type"],
        "is_default": True, "active": False,
    })
    assert r.status_code == 409, r.text
    todas = admin_client.get("/locations?incluir_inactivas=true").json()
    assert next(loc for loc in todas if loc["id"] == otra["id"])["active"] is True


def test_desactivar_la_sucursal_default_da_409(admin_client):
    default = _sucursal_default(admin_client)

    r = admin_client.put(f"/locations/{default['id']}", json={
        "name": default["name"], "location_type": default["location_type"],
        "is_default": True, "active": False,
    })

    assert r.status_code == 409, r.text
    # La frena la guarda previa del servicio («inactiva no puede ser la
    # predeterminada») antes de que el motor llegue a escribir.
    assert "predeterminada" in r.json()["detail"]
    # No quedó a medio camino: sigue activa.
    assert admin_client.get("/locations").json()[0]["active"] is True


def test_desactivar_sucursal_con_turno_abierto_da_409(admin_client):
    sucursal = _crear_sucursal(admin_client, "Sucursal con turno")
    caja_id = _cajas_de(admin_client, sucursal["id"])[0]["id"]
    abrir_turno(admin_client, caja_id=caja_id)

    r = admin_client.put(f"/locations/{sucursal['id']}", json={
        "name": sucursal["name"], "location_type": sucursal["location_type"],
        "is_default": False, "active": False,
    })

    assert r.status_code == 409, r.text
    assert "turno" in r.json()["detail"]
    activa = next(
        loc for loc in admin_client.get("/locations?incluir_inactivas=true").json()
        if loc["id"] == sucursal["id"]
    )
    assert activa["active"] is True


def test_desactivar_sucursal_sin_turno_abierto_funciona(admin_client):
    """Control positivo del test anterior: la guarda es por turno abierto, no
    por editar en general -- sin turno, desactivar una sucursal no-default
    anda."""
    sucursal = _crear_sucursal(admin_client, "Sucursal sin ventas")

    r = admin_client.put(f"/locations/{sucursal['id']}", json={
        "name": sucursal["name"], "location_type": sucursal["location_type"],
        "is_default": False, "active": False,
    })

    assert r.status_code == 200, r.text
    assert r.json()["active"] is False
    # Y desaparece del listado por defecto (activas), pero sigue en el que
    # incluye inactivas -- lo que necesita la pantalla de edición para poder
    # reactivarla después.
    assert sucursal["id"] not in [l["id"] for l in admin_client.get("/locations").json()]
    assert sucursal["id"] in [
        l["id"] for l in admin_client.get("/locations?incluir_inactivas=true").json()
    ]


def test_editar_sucursal_inexistente_da_404(admin_client):
    r = admin_client.put("/locations/999999", json={
        "name": "x", "location_type": "warehouse", "is_default": False, "active": True,
    })
    assert r.status_code == 404, r.text


def test_editar_con_nombre_vacio_da_422(admin_client):
    sucursal = _sucursal_default(admin_client)
    r = admin_client.put(f"/locations/{sucursal['id']}", json={
        "name": "   ", "location_type": "warehouse", "is_default": True, "active": True,
    })
    assert r.status_code == 422, r.text


def test_editar_con_tipo_vacio_da_422(admin_client):
    sucursal = _sucursal_default(admin_client)
    r = admin_client.put(f"/locations/{sucursal['id']}", json={
        "name": sucursal["name"], "location_type": "  ", "is_default": True, "active": True,
    })
    assert r.status_code == 422, r.text


def test_editar_sin_sesion_da_401(tmp_path):
    with https_client(create_app(destino_dominio(tmp_path / "ventalibra.db"))) as sin_sesion:
        r = sin_sesion.put("/locations/1", json={
            "name": "x", "location_type": "warehouse", "is_default": False, "active": True,
        })
        assert r.status_code == 401, r.text


def test_el_cajero_no_crea_ni_edita_sucursales_pero_las_lista(admin_client, staff_client):
    """Alta y edición, sólo admin (decisión del humano, 2026-09-17). El listado
    sigue abierto: el POS lo necesita para abrir turno."""
    sucursal = _crear_sucursal(admin_client, "Sucursal del admin")

    r = staff_client.post("/locations", json={"name": "Del cajero"})
    assert r.status_code == 403, r.text
    r = staff_client.put(f"/locations/{sucursal['id']}", json={
        "name": "Renombrada", "location_type": sucursal["location_type"],
        "is_default": False, "active": True,
    })
    assert r.status_code == 403, r.text

    assert staff_client.get("/locations").status_code == 200
    nombres = {loc["name"] for loc in admin_client.get("/locations").json()}
    assert "Del cajero" not in nombres and "Sucursal del admin" in nombres


def test_listar_sin_incluir_inactivas_no_cambia_lo_de_siempre(admin_client):
    """Control: el default de `GET /locations` sigue siendo sólo activas --
    no se rompió nada de lo que ya usaban el POS y el alta de cajas."""
    sucursal = _crear_sucursal(admin_client, "Sucursal a apagar")
    admin_client.put(f"/locations/{sucursal['id']}", json={
        "name": sucursal["name"], "location_type": sucursal["location_type"],
        "is_default": False, "active": False,
    })
    ids = [l["id"] for l in admin_client.get("/locations").json()]
    assert sucursal["id"] not in ids


def test_el_cambio_de_default_lo_ve_otra_conexion(admin_client):
    """🔴 `PUT /locations/{id}` escribía sin commitear: la respuesta mostraba el
    default nuevo (misma conexión) pero cada venta, que abre su propia conexión,
    seguía viendo el viejo y rechazaba con 422. Se lee ACÁ por una conexión
    distinta de la de la app, que es lo que hace una venta."""
    import psycopg
    from motor_de_test import TEST_DATABASE_URL

    nueva = _crear_sucursal(admin_client, "Sucursal Nueva")
    r = admin_client.put(f"/locations/{nueva['id']}", json={
        "name": nueva["name"], "location_type": "store", "is_default": True, "active": True,
    })
    assert r.status_code == 200, r.text
    with psycopg.connect(TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)) as otra:
        defaults = otra.execute("SELECT id FROM locations WHERE is_default = 1").fetchall()
    assert defaults == [(nueva["id"],)]


# ── Dos tipos, y como mínimo uno de cada uno (decisión del humano, 2026-09-25) ──


def _tipos_activos(client) -> list[str]:
    return sorted(loc["location_type"] for loc in client.get("/locations").json())


def _editar(client, loc: dict, **cambios):
    cuerpo = {"name": loc["name"], "location_type": loc["location_type"],
              "is_default": loc["is_default"], "active": True} | cambios
    return client.put(f"/locations/{loc['id']}", json=cuerpo)


def test_una_base_nueva_declara_una_sucursal_y_un_deposito(admin_client):
    assert _tipos_activos(admin_client) == ["store", "warehouse"]


def test_el_tipo_se_elige_entre_sucursal_y_deposito(admin_client):
    r = admin_client.post("/locations", json={"name": "Local", "location_type": "Negocio"})
    assert r.status_code == 422, r.text
    otra = _crear_sucursal(admin_client, "Otra")
    r = _editar(admin_client, otra, location_type="Negocio")
    assert r.status_code == 422, r.text


def test_no_se_deja_a_la_instancia_sin_su_unica_sucursal_o_deposito(admin_client):
    locs = admin_client.get("/locations").json()
    sucursal = next(loc for loc in locs if loc["location_type"] == "store")
    deposito = next(loc for loc in locs if loc["location_type"] == "warehouse")
    assert deposito["is_default"] is False  # el default es la sucursal sembrada

    for loc, cambio in ((deposito, {"active": False}), (deposito, {"location_type": "store"}),
                        (sucursal, {"location_type": "warehouse"})):
        r = _editar(admin_client, loc, **cambio)
        assert r.status_code == 409, (loc["name"], cambio, r.text)
        assert "como mínimo" in r.json()["detail"]
    assert _tipos_activos(admin_client) == ["store", "warehouse"]


def test_con_otro_deposito_se_puede_dar_de_baja_el_primero(admin_client):
    deposito = next(l for l in admin_client.get("/locations").json() if l["location_type"] == "warehouse")
    otro = admin_client.post("/locations", json={"name": "Depósito 2", "location_type": "warehouse"}).json()
    assert _editar(admin_client, deposito, active=False).status_code == 200
    assert otro["location_type"] == "warehouse"


def test_el_arranque_completa_el_tipo_que_falta_y_es_idempotente(admin_client):
    from app.services.locations import LocationService

    conn = admin_client.app.state.conn
    conn.execute("DELETE FROM locations WHERE location_type = 'warehouse'")
    conn.commit()
    servicio = LocationService(conn)
    assert servicio.asegurar_tipos_minimos() == ["Depósito 1"]
    assert servicio.asegurar_tipos_minimos() == []
    assert _tipos_activos(admin_client) == ["store", "warehouse"]
