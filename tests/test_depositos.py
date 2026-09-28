"""Depósitos con el router del motor (`/api/depositos`, fase 6, ADR-033; jerarquía, 2026-09-28).

Desde la jerarquía el stock vive sólo en los depósitos y **todo depósito pertenece a una sucursal**
(`locations.branch_id`). Las guardas de «a lo sumo un default», «no desactivar el default» y «no quitar el último
depósito activo de una sucursal» son del motor (`libracommerce.erp.catalogo`, ADR-012/013); la regla de este
producto —el depósito nace con su sucursal— vive en `app/depositos_ganchos.py`.

Las reglas de las sucursales (`/api/sucursales`) están en `test_sucursales.py`.
"""
from conftest import https_client
from motor_de_test import destino_dominio
from ventas_helpers import con_stock, crear_deposito, crear_item, crear_sucursal, sucursal_default

from app.main import create_app


def _deposito_default(client) -> dict:
    return next(d for d in client.get("/api/depositos").json() if d["es_default"])


def _editar(client, dep: dict, **cambios):
    cuerpo = {"nombre": dep["nombre"], "descripcion": dep["descripcion"] or "", "activo": True} | cambios
    return client.put(f"/api/depositos/{dep['id']}", json=cuerpo)


def test_editar_deposito_cambia_el_nombre(admin_client):
    deposito = crear_deposito(admin_client, "Depósito Norte")

    editado = _editar(admin_client, deposito, nombre="  Depósito Norte (renombrado)  ")

    assert editado.status_code == 200, editado.text
    # El nombre se guarda sin los espacios del padding -- mismo criterio que el resto de la familia.
    assert editado.json()["nombre"] == "Depósito Norte (renombrado)"


def test_marcar_default_desmarca_el_anterior(admin_client):
    """`set-default` en el depósito nuevo deja EXACTAMENTE un default."""
    viejo_default = _deposito_default(admin_client)
    nuevo = crear_deposito(admin_client, "Depósito Sur")

    r = admin_client.post(f"/api/depositos/{nuevo['id']}/set-default")
    assert r.status_code == 200, r.text
    assert r.json()["es_default"]

    depositos = admin_client.get("/api/depositos").json()
    assert [d["id"] for d in depositos if d["es_default"]] == [nuevo["id"]]
    assert not next(d for d in depositos if d["id"] == viejo_default["id"])["es_default"]


def test_no_se_marca_default_un_deposito_inactivo(admin_client):
    """Guarda del motor: un default inactivo le seguiría cargando stock en silencio a un depósito dado de baja."""
    otro = crear_deposito(admin_client, "Depósito Norte")
    assert _editar(admin_client, otro, activo=False).status_code == 200

    r = admin_client.post(f"/api/depositos/{otro['id']}/set-default")
    assert r.status_code == 422, r.text
    assert "inactivo" in r.json()["detail"]
    assert _deposito_default(admin_client)["id"] != otro["id"]


def test_desactivar_el_deposito_default_da_422_y_no_deja_nada_a_medias(admin_client):
    crear_deposito(admin_client, "Otro depósito")  # así no es el último de su sucursal
    default = _deposito_default(admin_client)

    r = _editar(admin_client, default, activo=False)

    assert r.status_code == 422, r.text
    assert "por defecto" in r.json()["detail"]
    assert _deposito_default(admin_client)["activo"]  # sigue activo


def test_no_se_desactiva_el_ultimo_deposito_activo_de_una_sucursal(admin_client):
    """Una sucursal nueva nace con UN depósito, que no es el default de la instancia: la guarda que frena es la del
    último depósito de su sucursal."""
    sucursal = crear_sucursal(admin_client, "Sucursal Norte")
    unico = next(d for d in admin_client.get("/api/depositos").json() if d["id"] == sucursal["deposito_predeterminado_id"])

    r = _editar(admin_client, unico, activo=False)

    assert r.status_code == 422, r.text
    assert "único depósito activo" in r.json()["detail"]


def test_con_otro_deposito_se_puede_dar_de_baja_uno(admin_client):
    extra = crear_deposito(admin_client, "Depósito 2")
    assert _editar(admin_client, extra, activo=False).status_code == 200


def test_editar_inexistente_da_404(admin_client):
    r = admin_client.put("/api/depositos/999999", json={"nombre": "x", "activo": True})
    assert r.status_code == 404, r.text


def test_editar_con_nombre_vacio_da_422(admin_client):
    deposito = _deposito_default(admin_client)
    r = admin_client.put(f"/api/depositos/{deposito['id']}", json={"nombre": "   ", "activo": True})
    assert r.status_code == 422, r.text


def test_editar_sin_sesion_da_401(tmp_path):
    with https_client(create_app(destino_dominio(tmp_path / "ventalibra.db"))) as sin_sesion:
        r = sin_sesion.put("/api/depositos/1", json={"nombre": "x", "activo": True})
        assert r.status_code == 401, r.text


def test_el_cajero_no_crea_edita_predetermina_ni_borra_pero_los_lista(admin_client, staff_client):
    """Alta, edición, predeterminado y baja, sólo admin (decisión del humano, 2026-09-17). El listado sigue abierto:
    el POS lo necesita."""
    deposito = crear_deposito(admin_client, "Depósito del admin")

    sucursal = sucursal_default(admin_client)["id"]
    assert staff_client.post("/api/depositos", json={"nombre": "Del cajero", "branch_id": sucursal}).status_code == 403
    assert staff_client.put(
        f"/api/depositos/{deposito['id']}", json={"nombre": "Renombrado", "activo": True}
    ).status_code == 403
    assert staff_client.post(f"/api/depositos/{deposito['id']}/set-default").status_code == 403
    assert staff_client.delete(f"/api/depositos/{deposito['id']}").status_code == 403

    assert staff_client.get("/api/depositos").status_code == 200
    nombres = {d["nombre"] for d in admin_client.get("/api/depositos").json()}
    assert "Del cajero" not in nombres and "Depósito del admin" in nombres


def test_el_cambio_de_default_lo_ve_otra_conexion(admin_client):
    """🔴 Un default que sólo ve la conexión de la app y no la de cada venta rechaza toda venta con 422. Se lee ACÁ
    por una conexión distinta, que es lo que hace una venta."""
    import psycopg
    from motor_de_test import TEST_DATABASE_URL

    nuevo = crear_deposito(admin_client, "Depósito Nuevo")
    r = admin_client.post(f"/api/depositos/{nuevo['id']}/set-default")
    assert r.status_code == 200, r.text
    with psycopg.connect(TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)) as otra:
        defaults = otra.execute("SELECT id FROM locations WHERE is_default = 1").fetchall()
    assert defaults == [(nuevo["id"],)]


# ── Todo depósito pertenece a una sucursal (jerarquía, 2026-09-28) ──────────


def test_un_deposito_nace_con_su_sucursal(admin_client):
    sucursal = sucursal_default(admin_client)

    r = admin_client.post("/api/depositos", json={"nombre": "Depósito Este", "branch_id": sucursal["id"]})

    assert r.status_code == 200, r.text
    assert r.json()["branch_id"] == sucursal["id"]


def test_un_deposito_sin_sucursal_da_422(admin_client):
    r = admin_client.post("/api/depositos", json={"nombre": "Suelto"})
    assert r.status_code == 422, r.text
    assert "sucursal" in r.json()["detail"]


def test_un_deposito_en_una_sucursal_inexistente_da_422(admin_client):
    r = admin_client.post("/api/depositos", json={"nombre": "Huérfano", "branch_id": 9999})
    assert r.status_code == 422, r.text


def test_el_listado_de_depositos_trae_la_sucursal_de_cada_uno(admin_client):
    sucursal = sucursal_default(admin_client)
    extra = crear_deposito(admin_client, "Depósito Extra", sucursal["id"])

    por_id = {d["id"]: d for d in admin_client.get("/api/depositos").json()}

    assert por_id[extra["id"]]["branch_id"] == sucursal["id"]
    assert por_id[sucursal["deposito_predeterminado_id"]]["branch_id"] == sucursal["id"]


# ── Baja ────────────────────────────────────────────────────────────────────


def test_un_deposito_sin_movimientos_se_elimina_y_con_movimientos_no(admin_client):
    vacio = crear_deposito(admin_client, "Depósito vacío")
    con_mov = crear_deposito(admin_client, "Depósito con stock")
    con_stock(admin_client, crear_item(admin_client), con_mov["id"], "3")

    assert admin_client.delete(f"/api/depositos/{vacio['id']}").json() == {"ok": True}
    r = admin_client.delete(f"/api/depositos/{con_mov['id']}")
    assert r.status_code == 422, r.text
    assert "movimientos" in r.json()["detail"]


def test_no_se_elimina_el_ultimo_deposito_activo_de_una_sucursal(admin_client):
    sucursal = crear_sucursal(admin_client, "Sucursal Norte")

    r = admin_client.delete(f"/api/depositos/{sucursal['deposito_predeterminado_id']}")

    assert r.status_code == 422, r.text
    assert "único depósito activo" in r.json()["detail"]


# ── Los routers propios se retiraron ──


def test_las_rutas_viejas_ya_no_existen(admin_client):
    for metodo, ruta in (("get", "/locations"), ("post", "/locations"), ("post", "/stock/adjustments"),
                         ("post", "/stock/transferir"), ("get", "/stock/por-deposito/grilla"),
                         ("get", "/stock/transferencias/historial")):
        r = getattr(admin_client, metodo)(ruta)
        assert r.status_code in (404, 405), f"{metodo.upper()} {ruta} -> {r.status_code}"
