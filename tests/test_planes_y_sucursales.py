"""Dos planes, y lo que los separa es lo fiscal y lo multisucursal (ADR-048, decisión del humano, 2026-09-29).

- **Básico**: un solo local. Todo lo demás (POS, stock, compras, caja, tesorería, dashboard...) libre.
- **Premium**: suma `facturacion` y `multisucursal` (más de una sucursal y la transferencia entre sucursales).

Lo que se prueba acá: el catálogo de planes (`plans.py`), el manejo de lo que ya no existe (plan `estandar`, módulo
`dashboard`), el gate del alta de una segunda sucursal y de la transferencia entre sucursales, que lo ya creado siga
funcionando en Básico, y los módulos que la SPA lee en `/auth/me`.

🔴 Los planes se aplican por el camino real (`plans.aplicar_plan_en_db` contra la base del test), no con
`set_enabled` a mano: es lo que hace el provisioning y lo que deja escrito la etiqueta del plan.
"""
import logging

import pytest
from motor_de_test import TEST_DATABASE_URL
from ventas_helpers import ajustar, crear_deposito, crear_item, crear_sucursal, stock, sucursal_default

import plans
from app.db import init_modules_schema


def _aplicar(client, plan: str) -> None:
    plans.aplicar_plan_en_db(TEST_DATABASE_URL, plan)


def _modulos(client) -> dict[str, dict]:
    filas = client.app.state.conn.execute("SELECT modulo, habilitado, plan FROM modulos").fetchall()
    return {f[0]: {"habilitado": bool(f[1]), "plan": f[2]} for f in filas}


# ── El catálogo de planes ────────────────────────────────────────────────────────────────────────────────────────────


def test_hay_dos_planes_con_sus_precios():
    assert plans.PLANES == ["basico", "premium"]
    assert plans.PLAN_LABELS == {"basico": "Básico", "premium": "Premium"}
    assert plans.PLAN_PRECIOS == {"basico": 20000, "premium": 55000}


def test_basico_no_gatea_nada_y_premium_suma_facturacion_y_multisucursal():
    assert plans.modulos_de_plan("basico") == set()
    assert plans.modulos_de_plan("premium") == {"facturacion", "multisucursal"}
    assert plans.TODOS_LOS_MODULOS == {"facturacion", "multisucursal"}


def test_el_dashboard_ya_no_es_un_modulo_gateable():
    assert "dashboard" not in plans.TODOS_LOS_MODULOS
    assert "dashboard" in plans.MODULOS_RETIRADOS
    for plan in plans.PLANES:
        assert "dashboard" not in plans.modulos_de_plan(plan)


def test_un_plan_retirado_se_resuelve_como_su_reemplazo_y_avisa(caplog):
    with caplog.at_level(logging.WARNING, logger="plans"):
        assert plans.modulos_de_plan("estandar") == plans.modulos_de_plan("premium")
    assert "estandar" in caplog.text
    assert "premium" in caplog.text


def test_un_plan_desconocido_no_se_aplica(admin_client):
    """Sin esto un typo apagaría TODOS los módulos de la instancia, facturación incluida."""
    antes = _modulos(admin_client)
    with pytest.raises(ValueError, match="premiun"):
        plans.aplicar_plan_en_db(TEST_DATABASE_URL, "premiun")
    assert _modulos(admin_client) == antes


def test_aplicar_el_plan_estandar_lo_reescribe_como_premium(admin_client, caplog):
    with caplog.at_level(logging.WARNING, logger="plans"):
        _aplicar(admin_client, "estandar")
    assert "estandar" in caplog.text
    assert _modulos(admin_client) == {
        "facturacion": {"habilitado": True, "plan": "premium"},
        "multisucursal": {"habilitado": True, "plan": "premium"},
    }


def test_aplicar_basico_apaga_los_dos_modulos(admin_client):
    _aplicar(admin_client, "basico")
    assert _modulos(admin_client) == {
        "facturacion": {"habilitado": False, "plan": "basico"},
        "multisucursal": {"habilitado": False, "plan": "basico"},
    }


# ── Instancias que ya existían: el arranque siembra el módulo nuevo según su plan ─────────────────────────────────────


def _como_instancia_anterior(client, plan: str, *, con_dashboard: bool) -> None:
    """Deja `modulos` como la tenía una instancia desplegada antes de ADR-048: sin la fila `multisucursal`, con la
    etiqueta de su plan y, si es del esquema viejo, con la fila `dashboard`."""
    conn = client.app.state.conn
    conn.execute("DELETE FROM modulos")
    conn.execute("INSERT INTO modulos (modulo, habilitado, plan) VALUES ('facturacion', ?, ?)",
                 (0 if plan == "basico" else 1, plan))
    if con_dashboard:
        conn.execute("INSERT INTO modulos (modulo, habilitado, plan) VALUES ('dashboard', ?, ?)",
                     (1 if plan == "premium" else 0, plan))
    conn.commit()


def test_una_instancia_basico_ya_desplegada_recibe_multisucursal_apagado(admin_client):
    """🔴 Sin esto el módulo nuevo se sembraría prendido en cada Básico existente y el gate no cortaría hasta que
    alguien reaplicara el plan a mano."""
    _como_instancia_anterior(admin_client, "basico", con_dashboard=True)

    init_modules_schema(admin_client.app.state.conn)

    assert _modulos(admin_client)["multisucursal"] == {"habilitado": False, "plan": "basico"}
    assert admin_client.app.state.modules.is_enabled("multisucursal") is False


def test_una_instancia_premium_ya_desplegada_recibe_multisucursal_prendido(admin_client):
    _como_instancia_anterior(admin_client, "premium", con_dashboard=True)

    init_modules_schema(admin_client.app.state.conn)

    assert _modulos(admin_client)["multisucursal"] == {"habilitado": True, "plan": "premium"}


def test_una_instancia_con_plan_estandar_opera_como_premium_y_avisa(admin_client, caplog):
    """La demo era la única con `estandar` guardado. No pierde la facturación que tenía y las sucursales que ya usaba
    (eran libres) siguen andando; y el arranque lo deja dicho en el log en vez de resolverlo en silencio."""
    _como_instancia_anterior(admin_client, "estandar", con_dashboard=True)

    with caplog.at_level(logging.WARNING, logger="plans"):
        init_modules_schema(admin_client.app.state.conn)

    fila = _modulos(admin_client)["multisucursal"]
    assert fila["habilitado"] is True
    assert "estandar" in caplog.text
    # La etiqueta guardada no se reescribe al arrancar: eso es del provisioning (`aplicar_plan_en_db`).
    assert _modulos(admin_client)["facturacion"]["plan"] == "estandar"


def test_una_base_nueva_arranca_con_todo_prendido_como_siempre(admin_client):
    assert _modulos(admin_client) == {
        "facturacion": {"habilitado": True, "plan": "premium"},
        "multisucursal": {"habilitado": True, "plan": "premium"},
    }


def test_la_fila_vieja_de_dashboard_no_corta_nada(admin_client):
    """Los planes viejos guardaban `dashboard` con `habilitado=0` en Básico: hoy la fila sobra y no se lee."""
    _como_instancia_anterior(admin_client, "basico", con_dashboard=True)
    init_modules_schema(admin_client.app.state.conn)

    assert _modulos(admin_client)["dashboard"]["habilitado"] is False
    assert admin_client.app.state.modules.is_enabled("dashboard") is True
    assert admin_client.get("/api/dashboard").status_code == 200


# ── El tablero es libre en los dos planes ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("plan", plans.PLANES)
def test_el_dashboard_se_abre_en_los_dos_planes(admin_client, plan):
    _aplicar(admin_client, plan)
    assert admin_client.get("/api/dashboard").status_code == 200


# ── Básico: un solo local ────────────────────────────────────────────────────────────────────────────────────────────


def test_basico_no_da_de_alta_una_segunda_sucursal(admin_client):
    sucursales_antes = admin_client.get("/api/sucursales").json()
    assert len(sucursales_antes) == 1
    _aplicar(admin_client, "basico")

    r = admin_client.post("/api/sucursales", json={"nombre": "Sucursal Este"})

    assert r.status_code == 403, r.text
    assert "multisucursal" in r.json()["detail"]  # el mismo vocabulario que `require_module`
    assert "Premium" in r.json()["detail"]
    assert admin_client.get("/api/sucursales").json() == sucursales_antes  # no se creó nada


def test_premium_da_de_alta_otra_sucursal(admin_client):
    _aplicar(admin_client, "premium")
    assert crear_sucursal(admin_client, "Sucursal Este")["nombre"] == "Sucursal Este"
    assert len(admin_client.get("/api/sucursales").json()) == 2


def test_el_gate_se_mira_en_cada_pedido_no_al_armar_la_app(admin_client):
    """Un cambio de plan con la app corriendo se ve en el pedido siguiente, igual que `require_module`."""
    _aplicar(admin_client, "basico")
    assert admin_client.post("/api/sucursales", json={"nombre": "A"}).status_code == 403
    _aplicar(admin_client, "premium")
    assert admin_client.post("/api/sucursales", json={"nombre": "A"}).status_code == 200
    _aplicar(admin_client, "basico")
    assert admin_client.post("/api/sucursales", json={"nombre": "B"}).status_code == 403


def test_basico_tampoco_reactiva_una_sucursal_mientras_hay_otra_activa(admin_client):
    vieja = crear_sucursal(admin_client, "Local viejo")
    baja = admin_client.put(f"/api/sucursales/{vieja['id']}", json={"nombre": "Local viejo", "activa": False})
    assert baja.status_code == 200, baja.text
    _aplicar(admin_client, "basico")

    r = admin_client.put(f"/api/sucursales/{vieja['id']}", json={"nombre": "Local viejo", "activa": True})

    assert r.status_code == 403, r.text
    assert "multisucursal" in r.json()["detail"]
    assert [s["activa"] for s in admin_client.get("/api/sucursales?solo_activas=false").json() if s["id"] == vieja["id"]] == [0]


def test_un_local_con_dos_depositos_sigue_siendo_un_local(admin_client):
    """La unidad del gate es la sucursal: agregar depósitos a la única sucursal, y mover mercadería entre ellos, es libre
    en Básico."""
    _aplicar(admin_client, "basico")
    principal = sucursal_default(admin_client)
    trastienda = crear_deposito(admin_client, "Trastienda", principal["id"])  # `crear_deposito` exige 200
    salon = principal["deposito_predeterminado_id"]
    item = crear_item(admin_client)
    assert ajustar(admin_client, item, salon, "10", motivo="conteo").status_code == 200

    r = admin_client.post("/api/depositos/transferir", json={
        "producto_id": item, "origen_id": salon, "destino_id": trastienda["id"], "cantidad": 4,
    })

    assert r.status_code == 200, r.text
    assert float(stock(admin_client, item, salon)) == 6.0
    assert float(stock(admin_client, item, trastienda["id"])) == 4.0


def _dos_sucursales_con_stock(client, cantidad="10"):
    """Dos sucursales (creadas mientras el plan lo permite) y un producto con stock en el depósito de la primera."""
    item = crear_item(client)
    origen = sucursal_default(client)["deposito_predeterminado_id"]
    destino = crear_sucursal(client, "Sucursal Este")["deposito_predeterminado_id"]
    assert ajustar(client, item, origen, cantidad, motivo="conteo").status_code == 200
    return item, origen, destino


def _transferir(client, item, origen, destino, cantidad=3):
    return client.post("/api/depositos/transferir", json={
        "producto_id": item, "origen_id": origen, "destino_id": destino, "cantidad": cantidad,
    })


def test_basico_no_transfiere_entre_sucursales(admin_client):
    item, origen, destino = _dos_sucursales_con_stock(admin_client)
    _aplicar(admin_client, "basico")

    r = _transferir(admin_client, item, origen, destino)

    assert r.status_code == 403, r.text
    assert "multisucursal" in r.json()["detail"]
    assert float(stock(admin_client, item, origen)) == 10.0  # no se movió nada
    assert float(stock(admin_client, item, destino)) == 0.0


def test_el_cajero_tampoco_transfiere_entre_sucursales_en_basico(admin_client, encargado_client):
    """La transferencia es de encargado, depósito y admin: el gate del plan corta a los dos."""
    item, origen, destino = _dos_sucursales_con_stock(admin_client)
    _aplicar(admin_client, "basico")

    assert _transferir(encargado_client, item, origen, destino).status_code == 403
    assert float(stock(admin_client, item, destino)) == 0.0


def test_premium_transfiere_entre_sucursales(admin_client, encargado_client):
    item, origen, destino = _dos_sucursales_con_stock(admin_client)
    _aplicar(admin_client, "premium")

    assert _transferir(admin_client, item, origen, destino, 3).status_code == 200
    assert _transferir(encargado_client, item, origen, destino, 2).status_code == 200
    assert float(stock(admin_client, item, origen)) == 5.0
    assert float(stock(admin_client, item, destino)) == 5.0


def test_una_transferencia_mal_formada_la_contesta_el_endpoint_no_el_gate(admin_client):
    """El gate sólo decide lo que puede resolver: un depósito que no existe o campos que faltan siguen siendo el 422 de
    siempre, con o sin plan."""
    item, origen, _ = _dos_sucursales_con_stock(admin_client)
    _aplicar(admin_client, "basico")

    assert _transferir(admin_client, item, origen, 999999).status_code == 422
    assert admin_client.post("/api/depositos/transferir", json={"producto_id": item}).status_code == 422
    assert admin_client.post("/api/depositos/transferir", json=[1, 2]).status_code == 422
    assert admin_client.post("/api/depositos/transferir", json={
        "producto_id": item, "origen_id": "x", "destino_id": origen, "cantidad": 1,
    }).status_code == 422


def test_el_resto_de_las_rutas_de_depositos_no_lee_ni_corta_nada_en_basico(admin_client):
    """El gate está montado sobre TODO el router de depósitos y sólo actúa sobre `POST …/transferir`."""
    _aplicar(admin_client, "basico")
    principal = sucursal_default(admin_client)

    assert admin_client.get("/api/depositos").status_code == 200
    assert admin_client.get("/api/depositos/transferencias").status_code == 200
    assert admin_client.post("/api/depositos", json={"nombre": "Freezer", "branch_id": principal["id"]}).status_code == 200


# ── Lo que ya existe no se rompe: una instalación con varias sucursales, en Básico ──────────────────────────────────────


def test_una_instalacion_con_varias_sucursales_sigue_leyendose_y_editandose_en_basico(admin_client, encargado_client):
    """La demo tiene tres ubicaciones. Pasar a Básico sólo impide crear más y cruzar mercadería: no borra ni oculta
    lo existente, ni impide editarlo, ni vender."""
    item, origen, destino = _dos_sucursales_con_stock(admin_client)
    tercera = crear_sucursal(admin_client, "Sucursal Norte")
    _aplicar(admin_client, "basico")

    # Se lee todo.
    for cliente in (admin_client, encargado_client):
        nombres = [s["nombre"] for s in cliente.get("/api/sucursales").json()]
        assert len(nombres) == 3 and "Sucursal Norte" in nombres
        assert len(cliente.get("/api/depositos").json()) == 3
    assert admin_client.get("/api/stock").status_code == 200
    assert admin_client.get(f"/api/depositos/{origen}/stock").status_code == 200

    # Se edita: renombrar, cambiar cuál es la predeterminada y dar de baja una (sin existencias, y sin ser la predeterminada).
    principal = sucursal_default(admin_client)
    r = admin_client.put(f"/api/sucursales/{tercera['id']}", json={"nombre": "Norte II", "activa": True})
    assert r.status_code == 200 and r.json()["nombre"] == "Norte II"
    assert admin_client.post(f"/api/sucursales/{tercera['id']}/set-default").status_code == 200
    assert admin_client.post(f"/api/sucursales/{principal['id']}/set-default").status_code == 200
    baja = admin_client.put(f"/api/sucursales/{tercera['id']}", json={"nombre": "Norte II", "activa": False})
    assert baja.status_code == 200, baja.text

    # Y sigue sin poder cruzar ni abrir otra.
    assert _transferir(admin_client, item, origen, destino).status_code == 403
    assert admin_client.post("/api/sucursales", json={"nombre": "Cuarta"}).status_code == 403


def test_una_venta_en_una_segunda_sucursal_sigue_andando_en_basico(admin_client):
    """El gate es de estructura (crear, cruzar), no de operación: vender en una sucursal que ya existía no se toca."""
    from ventas_helpers import abrir_turno, registrar_venta

    otra = crear_sucursal(admin_client, "Sucursal Este")
    item = crear_item(admin_client)
    assert ajustar(admin_client, item, otra["deposito_predeterminado_id"], "10", motivo="conteo").status_code == 200
    caja = admin_client.get(f"/api/cajas?sucursal_id={otra['id']}").json()
    assert caja, "la sucursal nueva recibe su primera caja"
    _aplicar(admin_client, "basico")

    abrir_turno(admin_client, caja_id=caja[0]["id"])
    venta = registrar_venta(admin_client, item, deposito_id=otra["deposito_predeterminado_id"])

    assert venta["id"] is not None


# ── Lo que la SPA lee ────────────────────────────────────────────────────────────────────────────────────────────────


def test_auth_me_lista_los_modulos_prendidos(admin_client):
    _aplicar(admin_client, "premium")
    assert admin_client.get("/auth/me").json()["modulos"] == ["facturacion", "multisucursal"]
    _aplicar(admin_client, "basico")
    assert admin_client.get("/auth/me").json()["modulos"] == []


def test_auth_me_incluye_los_addons_prendidos(admin_client):
    _aplicar(admin_client, "basico")
    admin_client.app.state.conn.execute(
        "INSERT INTO modulos (modulo, habilitado, plan) VALUES ('resguardo_externo', 1, 'addon')"
    )
    admin_client.app.state.conn.commit()

    assert admin_client.get("/auth/me").json()["modulos"] == ["resguardo_externo"]


def test_el_login_tambien_trae_los_modulos(admin_client):
    _aplicar(admin_client, "basico")
    r = admin_client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200 and r.json()["modulos"] == []


def test_si_no_se_pueden_leer_los_modulos_el_campo_se_omite_y_el_usuario_sale_igual(admin_client, monkeypatch):
    """No se manda `[]` (que escondería la facturación de un Premium por una falla pasajera): se omite y la SPA ofrece
    todo; el que corta de verdad es el backend."""
    def _roto(_modulo):
        raise RuntimeError("base caída")

    monkeypatch.setattr(admin_client.app.state.modules, "is_enabled", _roto)

    r = admin_client.get("/auth/me")

    assert r.status_code == 200
    assert "modulos" not in r.json()
    assert r.json()["username"] == "admin"


def test_los_ids_como_texto_no_saltean_el_gate_de_sucursales(admin_client):
    """El endpoint acepta los ids como texto numérico o flotante (pydantic en modo laxo): el gate los coacciona igual
    y no deja cruzar de sucursal en Básico (hallazgo de Codex, 2026-09-29)."""
    item, origen, destino = _dos_sucursales_con_stock(admin_client)
    _aplicar(admin_client, "basico")

    for o, d in ((str(origen), str(destino)), (float(origen), float(destino)), (origen, str(destino))):
        assert _transferir(admin_client, item, o, d).status_code == 403, (o, d)
    assert float(stock(admin_client, item, destino)) == 0.0
