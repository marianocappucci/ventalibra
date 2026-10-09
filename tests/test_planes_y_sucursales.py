"""Un único plan con todo incluido (ADR-072, decisión del humano, 2026-10-09; reemplaza a ADR-048 en lo de planes).

- **Plan único** (`unico`, «Plan único», $39.900 de lista, una sucursal incluida): trae `facturacion` y `multisucursal`
  prendidos, más todo lo que ya era libre (POS, stock, compras, caja, tesorería, dashboard...).
- **Retirados** (`basico`, `premium`, `estandar`): se resuelven como `unico` avisando, y una instancia que los tenga
  guardados se migra sola al arrancar (prende lo que tenía apagado; nunca apaga).

Lo que se prueba acá: el catálogo (`plans.py`), el manejo de lo que ya no existe (planes retirados, módulo `dashboard`),
la migración del arranque (`app.db.init_modules_schema`), que con el plan único se pueden dar de alta más sucursales y
transferir entre ellas, que el gate de «un solo local» sigue cortando si el módulo se apaga a mano (decisión
administrativa), y los módulos que la SPA lee en `/auth/me`.

🔴 Los planes se aplican por el camino real (`plans.aplicar_plan_en_db` contra la base del test), no con
`set_enabled` a mano: es lo que hace el provisioning y lo que deja escrito la etiqueta del plan. Apagar un módulo suelto
(`set_enabled`) es, a propósito, el otro camino: lo que haría un administrador, no un plan.
"""
import logging

import pytest
from motor_de_test import TEST_DATABASE_URL
from ventas_helpers import ajustar, crear_deposito, crear_item, crear_sucursal, stock, sucursal_default

import plans
from app.db import init_modules_schema

RETIRADOS = ["basico", "premium", "estandar"]


def _aplicar(client, plan: str) -> None:
    plans.aplicar_plan_en_db(TEST_DATABASE_URL, plan)


def _modulos(client) -> dict[str, dict]:
    filas = client.app.state.conn.execute("SELECT modulo, habilitado, plan FROM modulos").fetchall()
    return {f[0]: {"habilitado": bool(f[1]), "plan": f[2]} for f in filas}


def _apagar_multisucursal(client) -> None:
    """Lo que haría un administrador (no un plan): deja la instancia en un solo local."""
    client.app.state.modules.set_enabled("multisucursal", False)


TODO_PRENDIDO = {
    "facturacion": {"habilitado": True, "plan": "unico"},
    "multisucursal": {"habilitado": True, "plan": "unico"},
}


# ── El catálogo de planes ────────────────────────────────────────────────────────────────────────────────────────────


def test_hay_un_solo_plan_con_su_etiqueta_y_su_precio():
    assert plans.PLANES == ["unico"]
    assert plans.PLAN_LABELS == {"unico": "Plan único"}
    assert plans.PLAN_PRECIOS == {"unico": 39900}


def test_el_plan_unico_trae_facturacion_y_multisucursal():
    assert plans.modulos_de_plan("unico") == {"facturacion", "multisucursal"}
    # No se vacía: la SPA arma la pantalla con la lista `modulos` de `/auth/me`, que sale de acá.
    assert plans.TODOS_LOS_MODULOS == {"facturacion", "multisucursal"}


def test_el_dashboard_ya_no_es_un_modulo_gateable():
    assert "dashboard" not in plans.TODOS_LOS_MODULOS
    assert "dashboard" in plans.MODULOS_RETIRADOS
    for plan in plans.PLANES:
        assert "dashboard" not in plans.modulos_de_plan(plan)


@pytest.mark.parametrize("retirado", RETIRADOS)
def test_un_plan_retirado_se_resuelve_como_unico_y_avisa(retirado, caplog):
    with caplog.at_level(logging.WARNING, logger="plans"):
        assert plans.modulos_de_plan(retirado) == plans.modulos_de_plan("unico")
    assert retirado in caplog.text
    assert "unico" in caplog.text


def test_el_addon_sigue_afuera_del_plan_unico():
    assert plans.ADDONS == {"resguardo_externo"}
    assert not plans.ADDONS & plans.TODOS_LOS_MODULOS
    assert not plans.ADDONS & plans.modulos_de_plan("unico")


def test_un_plan_desconocido_no_se_aplica(admin_client):
    """Sin esto un typo apagaría TODOS los módulos de la instancia, facturación incluida."""
    antes = _modulos(admin_client)
    with pytest.raises(ValueError, match="unnico"):
        plans.aplicar_plan_en_db(TEST_DATABASE_URL, "unnico")
    assert _modulos(admin_client) == antes


def test_aplicar_el_plan_unico_deja_todo_prendido(admin_client):
    _aplicar(admin_client, "unico")
    assert _modulos(admin_client) == TODO_PRENDIDO


@pytest.mark.parametrize("retirado", RETIRADOS)
def test_aplicar_un_plan_retirado_lo_reescribe_como_unico_con_todo_prendido(admin_client, retirado, caplog):
    """`basico` tenía los dos módulos apagados: reaplicarlo ya no los apaga, los deja prendidos con la etiqueta vigente."""
    admin_client.app.state.modules.set_enabled("facturacion", False)
    admin_client.app.state.modules.set_enabled("multisucursal", False)

    with caplog.at_level(logging.WARNING, logger="plans"):
        _aplicar(admin_client, retirado)

    assert retirado in caplog.text
    assert _modulos(admin_client) == TODO_PRENDIDO


# ── Instancias que ya existían: el arranque las migra al plan único ────────────────────────────────────────────────────


def _como_instancia_anterior(client, plan: str, *, con_dashboard: bool, con_multisucursal: bool = True) -> None:
    """Deja `modulos` como la tenía una instancia desplegada con el plan `plan` (ya retirado): la etiqueta de su plan y,
    si es `basico`, los módulos APAGADOS; si es del esquema viejo, con la fila `dashboard`; y, si es de antes de
    ADR-048, sin la fila `multisucursal`."""
    encendido = 0 if plan == "basico" else 1
    conn = client.app.state.conn
    conn.execute("DELETE FROM modulos")
    modulos = ["facturacion"] + (["multisucursal"] if con_multisucursal else [])
    for modulo in modulos:
        conn.execute("INSERT INTO modulos (modulo, habilitado, plan) VALUES (?, ?, ?)", (modulo, encendido, plan))
    if con_dashboard:
        conn.execute("INSERT INTO modulos (modulo, habilitado, plan) VALUES ('dashboard', ?, ?)",
                     (1 if plan == "premium" else 0, plan))
    conn.commit()


def test_una_instancia_basico_ya_desplegada_queda_con_todo_prendido_y_etiqueta_unico(admin_client, caplog):
    """🔴 Una instancia guardada como `basico` tiene facturación y sucursales APAGADAS. Si el arranque sólo avisara,
    quedaría así para siempre aunque el producto ya no tenga ese plan: el arranque tiene que migrarla."""
    _como_instancia_anterior(admin_client, "basico", con_dashboard=True)
    assert _modulos(admin_client)["facturacion"]["habilitado"] is False  # el punto de partida es el que se dice

    with caplog.at_level(logging.WARNING):
        init_modules_schema(admin_client.app.state.conn)

    modulos = _modulos(admin_client)
    assert {m: modulos[m] for m in plans.TODOS_LOS_MODULOS} == TODO_PRENDIDO
    assert admin_client.app.state.modules.is_enabled("multisucursal") is True
    assert admin_client.app.state.modules.is_enabled("facturacion") is True
    # Dice qué migró: el plan de partida, el vigente y los módulos que prendió.
    assert "basico" in caplog.text and "unico" in caplog.text
    assert "facturacion" in caplog.text and "multisucursal" in caplog.text


@pytest.mark.parametrize("retirado", ["premium", "estandar"])
def test_una_instancia_premium_o_estandar_ya_desplegada_migra_a_unico_sin_perder_nada(admin_client, retirado):
    """No tenían nada apagado: sólo cambia la etiqueta. `estandar` (la demo lo tuvo) tampoco pierde lo que usaba."""
    _como_instancia_anterior(admin_client, retirado, con_dashboard=True)

    init_modules_schema(admin_client.app.state.conn)

    modulos = _modulos(admin_client)
    assert {m: modulos[m] for m in plans.TODOS_LOS_MODULOS} == TODO_PRENDIDO


def test_una_instancia_basico_anterior_a_multisucursal_recibe_los_dos_modulos_prendidos(admin_client):
    """La que sólo tenía la fila `facturacion` (apagada): se prende y el módulo que faltaba se siembra prendido."""
    _como_instancia_anterior(admin_client, "basico", con_dashboard=False, con_multisucursal=False)

    init_modules_schema(admin_client.app.state.conn)

    assert _modulos(admin_client) == TODO_PRENDIDO


def test_la_migracion_es_idempotente_y_no_vuelve_a_avisar(admin_client, caplog):
    _como_instancia_anterior(admin_client, "basico", con_dashboard=True)
    init_modules_schema(admin_client.app.state.conn)
    despues_de_migrar = _modulos(admin_client)
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        init_modules_schema(admin_client.app.state.conn)

    assert _modulos(admin_client) == despues_de_migrar
    assert "basico" not in caplog.text


def test_la_migracion_solo_prende_nunca_apaga(admin_client):
    """Una instancia que ya es `unico` y a la que un administrador le apagó un módulo no se toca al arrancar."""
    _apagar_multisucursal(admin_client)

    init_modules_schema(admin_client.app.state.conn)

    assert _modulos(admin_client)["multisucursal"] == {"habilitado": False, "plan": "unico"}


def test_la_migracion_no_toca_los_addons(admin_client):
    """El add-on es un servicio aparte (`plan='addon'`): ni se prende ni se reetiqueta al migrar el plan."""
    _como_instancia_anterior(admin_client, "basico", con_dashboard=True)
    admin_client.app.state.conn.execute(
        "INSERT INTO modulos (modulo, habilitado, plan) VALUES ('resguardo_externo', 0, 'addon')"
    )
    admin_client.app.state.conn.commit()

    init_modules_schema(admin_client.app.state.conn)

    modulos = _modulos(admin_client)
    assert modulos["resguardo_externo"] == {"habilitado": False, "plan": "addon"}
    assert {m: modulos[m] for m in plans.TODOS_LOS_MODULOS} == TODO_PRENDIDO
    assert admin_client.app.state.modules.is_enabled("resguardo_externo") is False


def test_con_planes_mezclados_el_arranque_no_adivina(admin_client):
    """Si las filas no dicen un solo plan no se sabe cuál migrar: se deja lo que hay."""
    _como_instancia_anterior(admin_client, "basico", con_dashboard=False)
    admin_client.app.state.conn.execute("UPDATE modulos SET plan = 'unico' WHERE modulo = 'multisucursal'")
    admin_client.app.state.conn.commit()
    antes = _modulos(admin_client)

    init_modules_schema(admin_client.app.state.conn)

    assert _modulos(admin_client) == antes


def test_con_un_plan_desconocido_el_arranque_no_adivina(admin_client):
    _como_instancia_anterior(admin_client, "basico", con_dashboard=False)
    admin_client.app.state.conn.execute("UPDATE modulos SET plan = 'raro'")
    admin_client.app.state.conn.commit()
    antes = _modulos(admin_client)

    init_modules_schema(admin_client.app.state.conn)

    assert _modulos(admin_client) == antes


def test_una_base_nueva_arranca_con_todo_prendido_y_plan_unico(admin_client):
    assert _modulos(admin_client) == TODO_PRENDIDO


def test_la_fila_vieja_de_dashboard_no_corta_nada(admin_client):
    """Los planes viejos guardaban `dashboard` con `habilitado=0` en Básico: hoy la fila sobra y no se lee, y la
    migración no se la lleva puesta (sigue ahí, con la etiqueta vigente)."""
    _como_instancia_anterior(admin_client, "basico", con_dashboard=True)
    init_modules_schema(admin_client.app.state.conn)

    assert _modulos(admin_client)["dashboard"] == {"habilitado": False, "plan": "unico"}
    assert admin_client.app.state.modules.is_enabled("dashboard") is True
    assert admin_client.get("/api/dashboard").status_code == 200


# ── El tablero es libre ──────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("plan", plans.PLANES + RETIRADOS)
def test_el_dashboard_se_abre_con_cualquier_plan(admin_client, plan):
    _aplicar(admin_client, plan)
    assert admin_client.get("/api/dashboard").status_code == 200


# ── Plan único: más de una sucursal ──────────────────────────────────────────────────────────────────────────────────


def test_el_plan_unico_da_de_alta_otra_sucursal(admin_client):
    _aplicar(admin_client, "unico")
    assert crear_sucursal(admin_client, "Sucursal Este")["nombre"] == "Sucursal Este"
    assert len(admin_client.get("/api/sucursales").json()) == 2


def test_una_base_nueva_ya_deja_dar_de_alta_otra_sucursal(admin_client):
    """Sin aplicar ningún plan: ya no hay un plan que lo impida."""
    assert crear_sucursal(admin_client, "Sucursal Este")["nombre"] == "Sucursal Este"
    assert len(admin_client.get("/api/sucursales").json()) == 2


def test_una_instancia_basico_migrada_da_de_alta_otra_sucursal(admin_client):
    """El caso que motivó la migración: antes de ADR-072 esta instancia daba 403 y ahora no."""
    _como_instancia_anterior(admin_client, "basico", con_dashboard=True)
    assert admin_client.post("/api/sucursales", json={"nombre": "Antes del arranque"}).status_code == 403
    init_modules_schema(admin_client.app.state.conn)

    assert crear_sucursal(admin_client, "Después del arranque")["nombre"] == "Después del arranque"


# ── Si el módulo se apaga a mano: un solo local ──────────────────────────────────────────────────────────────────────


def test_sin_multisucursal_no_da_de_alta_una_segunda_sucursal(admin_client):
    sucursales_antes = admin_client.get("/api/sucursales").json()
    assert len(sucursales_antes) == 1
    _apagar_multisucursal(admin_client)

    r = admin_client.post("/api/sucursales", json={"nombre": "Sucursal Este"})

    assert r.status_code == 403, r.text
    assert "multisucursal" in r.json()["detail"]  # el mismo vocabulario que `require_module`
    assert "no habilitado en esta instancia" in r.json()["detail"]
    assert "Premium" not in r.json()["detail"]  # ya no hay planes por los que pagar más
    assert admin_client.get("/api/sucursales").json() == sucursales_antes  # no se creó nada


def test_el_gate_se_mira_en_cada_pedido_no_al_armar_la_app(admin_client):
    """Un cambio de módulos con la app corriendo se ve en el pedido siguiente, igual que `require_module`."""
    _apagar_multisucursal(admin_client)
    assert admin_client.post("/api/sucursales", json={"nombre": "A"}).status_code == 403
    _aplicar(admin_client, "unico")
    assert admin_client.post("/api/sucursales", json={"nombre": "A"}).status_code == 200
    _apagar_multisucursal(admin_client)
    assert admin_client.post("/api/sucursales", json={"nombre": "B"}).status_code == 403


def test_sin_multisucursal_tampoco_reactiva_una_sucursal_mientras_hay_otra_activa(admin_client):
    vieja = crear_sucursal(admin_client, "Local viejo")
    baja = admin_client.put(f"/api/sucursales/{vieja['id']}", json={"nombre": "Local viejo", "activa": False})
    assert baja.status_code == 200, baja.text
    _apagar_multisucursal(admin_client)

    r = admin_client.put(f"/api/sucursales/{vieja['id']}", json={"nombre": "Local viejo", "activa": True})

    assert r.status_code == 403, r.text
    assert "multisucursal" in r.json()["detail"]
    assert [s["activa"] for s in admin_client.get("/api/sucursales?solo_activas=false").json() if s["id"] == vieja["id"]] == [0]


def test_un_local_con_dos_depositos_sigue_siendo_un_local(admin_client):
    """La unidad del gate es la sucursal: agregar depósitos a la única sucursal, y mover mercadería entre ellos, es libre
    sin `multisucursal`."""
    _apagar_multisucursal(admin_client)
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


def test_sin_multisucursal_no_transfiere_entre_sucursales(admin_client):
    item, origen, destino = _dos_sucursales_con_stock(admin_client)
    _apagar_multisucursal(admin_client)

    r = _transferir(admin_client, item, origen, destino)

    assert r.status_code == 403, r.text
    assert "multisucursal" in r.json()["detail"]
    assert float(stock(admin_client, item, origen)) == 10.0  # no se movió nada
    assert float(stock(admin_client, item, destino)) == 0.0


def test_el_cajero_tampoco_transfiere_entre_sucursales_sin_multisucursal(admin_client, encargado_client):
    """La transferencia es de encargado, depósito y admin: el gate del plan corta a los dos."""
    item, origen, destino = _dos_sucursales_con_stock(admin_client)
    _apagar_multisucursal(admin_client)

    assert _transferir(encargado_client, item, origen, destino).status_code == 403
    assert float(stock(admin_client, item, destino)) == 0.0


def test_el_plan_unico_transfiere_entre_sucursales(admin_client, encargado_client):
    item, origen, destino = _dos_sucursales_con_stock(admin_client)
    _aplicar(admin_client, "unico")

    assert _transferir(admin_client, item, origen, destino, 3).status_code == 200
    assert _transferir(encargado_client, item, origen, destino, 2).status_code == 200
    assert float(stock(admin_client, item, origen)) == 5.0
    assert float(stock(admin_client, item, destino)) == 5.0


def test_una_transferencia_mal_formada_la_contesta_el_endpoint_no_el_gate(admin_client):
    """El gate sólo decide lo que puede resolver: un depósito que no existe o campos que faltan siguen siendo el 422 de
    siempre, con o sin plan."""
    item, origen, _ = _dos_sucursales_con_stock(admin_client)
    _apagar_multisucursal(admin_client)

    assert _transferir(admin_client, item, origen, 999999).status_code == 422
    assert admin_client.post("/api/depositos/transferir", json={"producto_id": item}).status_code == 422
    assert admin_client.post("/api/depositos/transferir", json=[1, 2]).status_code == 422
    assert admin_client.post("/api/depositos/transferir", json={
        "producto_id": item, "origen_id": "x", "destino_id": origen, "cantidad": 1,
    }).status_code == 422


def test_el_resto_de_las_rutas_de_depositos_no_lee_ni_corta_nada_sin_multisucursal(admin_client):
    """El gate está montado sobre TODO el router de depósitos y sólo actúa sobre `POST …/transferir`."""
    _apagar_multisucursal(admin_client)
    principal = sucursal_default(admin_client)

    assert admin_client.get("/api/depositos").status_code == 200
    assert admin_client.get("/api/depositos/transferencias").status_code == 200
    assert admin_client.post("/api/depositos", json={"nombre": "Freezer", "branch_id": principal["id"]}).status_code == 200


# ── Lo que ya existe no se rompe: una instalación con varias sucursales, sin `multisucursal` ───────────────────────────


def test_una_instalacion_con_varias_sucursales_sigue_leyendose_y_editandose_sin_multisucursal(admin_client, encargado_client):
    """La demo tiene tres ubicaciones. Apagar `multisucursal` sólo impide crear más y cruzar mercadería: no borra ni oculta
    lo existente, ni impide editarlo, ni vender."""
    item, origen, destino = _dos_sucursales_con_stock(admin_client)
    tercera = crear_sucursal(admin_client, "Sucursal Norte")
    _apagar_multisucursal(admin_client)

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


def test_una_venta_en_una_segunda_sucursal_sigue_andando_sin_multisucursal(admin_client):
    """El gate es de estructura (crear, cruzar), no de operación: vender en una sucursal que ya existía no se toca."""
    from ventas_helpers import abrir_turno, registrar_venta

    otra = crear_sucursal(admin_client, "Sucursal Este")
    item = crear_item(admin_client)
    assert ajustar(admin_client, item, otra["deposito_predeterminado_id"], "10", motivo="conteo").status_code == 200
    caja = admin_client.get(f"/api/cajas?sucursal_id={otra['id']}").json()
    assert caja, "la sucursal nueva recibe su primera caja"
    _apagar_multisucursal(admin_client)

    abrir_turno(admin_client, caja_id=caja[0]["id"])
    venta = registrar_venta(admin_client, item, deposito_id=otra["deposito_predeterminado_id"])

    assert venta["id"] is not None


# ── Lo que la SPA lee ────────────────────────────────────────────────────────────────────────────────────────────────


def test_auth_me_lista_los_modulos_prendidos(admin_client):
    _aplicar(admin_client, "unico")
    assert admin_client.get("/auth/me").json()["modulos"] == ["facturacion", "multisucursal"]
    _apagar_multisucursal(admin_client)
    assert admin_client.get("/auth/me").json()["modulos"] == ["facturacion"]
    admin_client.app.state.modules.set_enabled("facturacion", False)
    assert admin_client.get("/auth/me").json()["modulos"] == []


def test_auth_me_incluye_los_addons_prendidos(admin_client):
    _aplicar(admin_client, "unico")
    admin_client.app.state.modules.set_enabled("facturacion", False)
    _apagar_multisucursal(admin_client)
    admin_client.app.state.conn.execute(
        "INSERT INTO modulos (modulo, habilitado, plan) VALUES ('resguardo_externo', 1, 'addon')"
    )
    admin_client.app.state.conn.commit()

    assert admin_client.get("/auth/me").json()["modulos"] == ["resguardo_externo"]


def test_el_login_tambien_trae_los_modulos(admin_client):
    _aplicar(admin_client, "unico")
    r = admin_client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200 and r.json()["modulos"] == ["facturacion", "multisucursal"]
    _apagar_multisucursal(admin_client)
    r = admin_client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200 and r.json()["modulos"] == ["facturacion"]


def test_si_no_se_pueden_leer_los_modulos_el_campo_se_omite_y_el_usuario_sale_igual(admin_client, monkeypatch):
    """No se manda `[]` (que escondería la facturación de la instancia por una falla pasajera): se omite y la SPA ofrece
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
    y no deja cruzar de sucursal sin `multisucursal` (hallazgo de Codex, 2026-09-29)."""
    item, origen, destino = _dos_sucursales_con_stock(admin_client)
    _apagar_multisucursal(admin_client)

    for o, d in ((str(origen), str(destino)), (float(origen), float(destino)), (origen, str(destino))):
        assert _transferir(admin_client, item, o, d).status_code == 403, (o, d)
    assert float(stock(admin_client, item, destino)) == 0.0
