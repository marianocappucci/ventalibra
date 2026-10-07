"""Sucursales con el router del motor (`/api/sucursales`, jerarquía, 2026-09-28).

Una sucursal es una entidad propia (`branches`) y su stock vive en sus depósitos. Del motor (ADR-012/013): nace con su
primer depósito, no se da de baja con existencias, y la baja arrastra a sus depósitos. Acá, las reglas de VentaLibra
(`app/depositos_ganchos.py`): sólo admin escribe, la última sucursal activa no se desactiva, una sucursal con turno
abierto tampoco, y la sucursal nueva recibe su caja.
"""
from test_cajas import _cajas_de
from ventas_helpers import abrir_turno, con_stock, crear_deposito, crear_item, crear_sucursal, sucursal_default


def _poner(client, sucursal: dict, **cambios):
    cuerpo = {"nombre": sucursal["nombre"], "activa": True} | cambios
    return client.put(f"/api/sucursales/{sucursal['id']}", json=cuerpo)


def _depositos_de(client, sucursal_id: int) -> list[dict]:
    return [d for d in client.get("/api/depositos").json() if d["branch_id"] == sucursal_id]


def test_una_base_nueva_declara_una_sucursal_con_su_deposito(admin_client):
    sucursal = sucursal_default(admin_client)

    depositos = _depositos_de(admin_client, sucursal["id"])

    assert [d["id"] for d in depositos] == [sucursal["deposito_predeterminado_id"]]
    assert depositos[0]["activo"]
    assert depositos[0]["es_default"]  # el default de la instancia: de ahí descuentan las ventas sin depósito


def test_la_sucursal_nueva_recibe_su_deposito_y_su_caja(admin_client):
    sucursal = crear_sucursal(admin_client, "Sucursal Este")

    assert len(_depositos_de(admin_client, sucursal["id"])) == 1
    assert len(_cajas_de(admin_client, sucursal["id"])) == 1


def test_el_nombre_del_primer_deposito_se_puede_elegir(admin_client):
    sucursal = crear_sucursal(admin_client, "Sucursal Oeste", deposito="Trastienda")

    assert [d["nombre"] for d in _depositos_de(admin_client, sucursal["id"])] == ["Trastienda"]


def test_el_listado_cuenta_los_depositos_activos(admin_client):
    sucursal = crear_sucursal(admin_client, "Sucursal Sur")
    crear_deposito(admin_client, "Depósito Sur 2", sucursal["id"])

    fila = next(s for s in admin_client.get("/api/sucursales").json() if s["id"] == sucursal["id"])

    assert fila["depositos"] == 2


def test_sin_sesion_o_como_cajero_no_se_escribe_pero_se_lista(admin_client, cajero_client):
    sucursal = crear_sucursal(admin_client, "Sucursal del admin")

    assert cajero_client.post("/api/sucursales", json={"nombre": "Del cajero"}).status_code == 403
    assert cajero_client.put(
        f"/api/sucursales/{sucursal['id']}", json={"nombre": "Renombrada", "activa": True}
    ).status_code == 403
    assert cajero_client.post(f"/api/sucursales/{sucursal['id']}/set-default").status_code == 403
    assert cajero_client.post(
        f"/api/sucursales/{sucursal['id']}/deposito-predeterminado",
        json={"deposito_id": sucursal["deposito_predeterminado_id"]},
    ).status_code == 403

    nombres = {s["nombre"] for s in cajero_client.get("/api/sucursales").json()}
    assert "Sucursal del admin" in nombres and "Del cajero" not in nombres


def test_desactivar_la_sucursal_default_da_422(admin_client):
    crear_sucursal(admin_client, "Otra sucursal")  # así no es la última
    default = sucursal_default(admin_client)

    r = _poner(admin_client, default, activa=False)

    assert r.status_code == 422, r.text
    assert "por defecto" in r.json()["detail"]
    assert sucursal_default(admin_client)["activa"]


def test_no_se_desactiva_la_ultima_sucursal_activa(admin_client):
    unica = sucursal_default(admin_client)

    r = _poner(admin_client, unica, activa=False)

    assert r.status_code == 409, r.text
    assert "como mínimo una sucursal" in r.json()["detail"]


def test_desactivar_sucursal_con_turno_abierto_da_409(admin_client):
    sucursal = crear_sucursal(admin_client, "Sucursal con turno")
    abrir_turno(admin_client, caja_id=_cajas_de(admin_client, sucursal["id"])[0]["id"])

    r = _poner(admin_client, sucursal, activa=False)

    assert r.status_code == 409, r.text
    assert "turno" in r.json()["detail"]
    assert next(s for s in admin_client.get("/api/sucursales").json() if s["id"] == sucursal["id"])["activa"]


def test_la_baja_de_una_sucursal_sin_ventas_da_de_baja_sus_depositos(admin_client):
    """Control positivo del anterior, y la baja arrastra a los depósitos (ADR-013)."""
    sucursal = crear_sucursal(admin_client, "Sucursal sin ventas")
    crear_deposito(admin_client, "Depósito extra", sucursal["id"])

    r = _poner(admin_client, sucursal, activa=False)

    assert r.status_code == 200, r.text
    assert not r.json()["activa"]
    assert not any(d["activo"] for d in _depositos_de(admin_client, sucursal["id"]))


def test_no_se_da_de_baja_una_sucursal_con_existencias(admin_client):
    sucursal = crear_sucursal(admin_client, "Sucursal con stock")
    con_stock(admin_client, crear_item(admin_client), sucursal["deposito_predeterminado_id"], "5")

    r = _poner(admin_client, sucursal, activa=False)

    assert r.status_code == 422, r.text
    assert "existencias" in r.json()["detail"]
    assert all(d["activo"] for d in _depositos_de(admin_client, sucursal["id"]))


def test_reactivar_una_sucursal_reactiva_su_deposito_y_conserva_su_caja(admin_client):
    sucursal = crear_sucursal(admin_client, "Sucursal que vuelve")
    assert _poner(admin_client, sucursal, activa=False).status_code == 200

    r = _poner(admin_client, sucursal, activa=True)

    assert r.status_code == 200, r.text
    activos = [d for d in _depositos_de(admin_client, sucursal["id"]) if d["activo"]]
    assert [d["id"] for d in activos] == [sucursal["deposito_predeterminado_id"]]
    assert len(_cajas_de(admin_client, sucursal["id"])) == 1


def test_editar_inexistente_da_404(admin_client):
    r = admin_client.put("/api/sucursales/999999", json={"nombre": "x", "activa": True})
    assert r.status_code == 404, r.text
