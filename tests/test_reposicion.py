"""Reposición sugerida con el router del motor (`/api/reportes/reposicion`, roadmap de producto B-3, ADR-051).

`libracommerce.web.reposicion_router.build_reposicion_router` (v0.28.0), sólo lectura: la cuenta (rotación, cobertura, el sesgo
por quiebres, qué es una orden «en camino», cómo se reparte por sucursal) es del motor y se prueba allá a fondo. Acá se prueba el
CABLEADO: que está montado, que lo ven el admin y el encargado y nadie más (capacidad `reposicion.ver`), que sobre los datos
reales de este producto —productos con `stock_minimo`, ventas de `POST /api/ventas`, una orden de compra abierta— da lo que dice,
que la sucursal por parámetro filtra, que no hay gate de plan y que la respuesta **no lleva costos**.

Los números del escenario, a mano (`DIAS_ROTACION=30`, `DIAS_COBERTURA=15`, `PLAZO_ENTREGA_DIAS=3`): la instancia es nueva, así que
el saldo de hoy es lo único que existe y los 29 días anteriores no cuentan (no hubo stock ni ventas): la muestra es de 1 día y el
motor divide por 7 (`_MIN_DIAS_DE_MUESTRA`). 7 unidades vendidas -> rotación de 1 por día; horizonte 15 + 3 = 18 días -> necesidad
18; hay 13 y vienen 4 -> por rotación faltarían 1, pero el mínimo (30) manda: 30 - 13 - 4 = 13.
"""
import re

import pytest
from conftest import https_client
from ventas_helpers import abrir_turno, crear_sucursal, deposito_default, registrar_venta, sucursal_default

#: Un costo que ninguna otra cifra del escenario repite: si aparece en la respuesta, se filtró.
COSTO = "731.42"
PRECIO = "1500.00"

ROLES_SIN_ACCESO = ("staff", "vendedor", "cajero")
RUTAS = ("/api/reportes/reposicion", "/api/reportes/reposicion/export")


def _entrar(admin_client, rol):
    """Un usuario de ese rol, logueado en la misma app que el admin."""
    creado = admin_client.post("/users", json={
        "username": f"u-{rol}", "name": rol.title(), "password": "clave-larga-1", "role": rol,
    })
    assert creado.status_code == 201, creado.text
    cliente = https_client(admin_client.app)
    assert cliente.post("/auth/login", json={"username": f"u-{rol}", "password": "clave-larga-1"}).status_code == 200
    return cliente


@pytest.fixture
def escenario(admin_client):
    """Yerba con mínimo 30, 20 cargadas, 7 vendidas hoy y 4 en una orden de compra abierta (sin sucursal); más un producto que
    no tiene nada que pedir, y una sucursal nueva sin movimientos."""
    c = admin_client
    c.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    assert c.post("/catalog/categories", json={"name": "Almacén"}).status_code == 200
    yerba = c.post("/api/productos", json={
        "nombre": "Yerba 1kg", "unidad": "u", "precio_venta": PRECIO, "precio_costo": COSTO, "stock_minimo": 30,
        "codigo": "YERBA-1", "categoria": "Almacén",
    })
    assert yerba.status_code == 200, yerba.text
    yerba = yerba.json()["id"]
    sobrado = c.post("/api/productos", json={
        "nombre": "Fideos 500g", "unidad": "u", "precio_venta": PRECIO, "precio_costo": "400.00", "stock_minimo": 1,
    }).json()["id"]
    deposito = deposito_default(c)
    for producto, cantidad in ((yerba, 20), (sobrado, 500)):
        assert c.post(f"/api/stock/{producto}/ajuste", json={
            "modo": "entrada", "cantidad": cantidad, "deposito_id": deposito, "referencia": "carga",
        }).status_code == 200
    abrir_turno(c)
    registrar_venta(c, yerba, precio=PRECIO, cantidad="7")

    proveedor = c.post("/api/proveedores", json={"nombre": "Distribuidora SA"}).json()["id"]
    orden = c.post("/api/purchase-orders", json={"proveedor_id": proveedor}).json()["id"]
    linea = c.post(f"/api/purchase-orders/{orden}/items", json={
        "item_id": yerba, "quantity_ordered": "4", "unit_cost": "543.21",
    })
    assert linea.status_code == 200, linea.text

    return {
        "yerba": yerba, "sobrado": sobrado, "sucursal": sucursal_default(c)["id"],
        "otra_sucursal": crear_sucursal(c, "Sucursal Norte", deposito="Norte")["id"],
    }


@pytest.fixture(params=["admin", "encargado"])
def gerencia(request, admin_client):
    """Un cliente de cada rol que tiene `reposicion.ver`."""
    return admin_client if request.param == "admin" else _entrar(admin_client, "encargado")


def _reposicion(cliente, **params):
    r = cliente.get("/api/reportes/reposicion", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_admin_y_encargado_ven_que_pedir_con_datos_reales(gerencia, escenario):
    m = _reposicion(gerencia)
    (p,) = m["productos"]  # los Fideos (500 en stock, mínimo 1) no hay que pedirlos: `solo_a_pedir` es True
    assert (m["dias_rotacion"], m["dias_cobertura"], m["plazo_entrega_dias"], m["sucursal_id"], m["solo_a_pedir"]) == (
        30, 15, 3, None, True)
    assert p["producto_id"] == escenario["yerba"] and p["nombre"] == "Yerba 1kg" and p["codigo"] == "YERBA-1"
    assert (p["stock"], p["en_camino"], p["stock_minimo"], p["unidades_vendidas"]) == (13.0, 4.0, 30.0, 7.0)
    assert p["rotacion_diaria"] == 1.0 and p["sugerido"] == 13 and p["motivo"] == "ambos"
    assert p["sin_ventas"] is False and p["unidad"] == "u"
    # Posible quiebre: en 29 de los 30 días de la ventana no hubo stock (la instancia es nueva), así que la rotación es una estimación.
    assert p["posible_quiebre"] is True and p["dias_con_stock"] == 1 and p["cobertura_dias"] == 13.0
    assert m["resumen"] == {"productos": 1, "a_pedir": 1, "posible_quiebre": 1, "sin_ventas": 0}


def test_solo_a_pedir_falso_trae_tambien_lo_que_no_hay_que_pedir(admin_client, escenario):
    m = _reposicion(admin_client, solo_a_pedir="false")
    por_id = {p["producto_id"]: p for p in m["productos"]}
    assert set(por_id) == {escenario["yerba"], escenario["sobrado"]}
    assert por_id[escenario["sobrado"]]["sugerido"] == 0 and por_id[escenario["sobrado"]]["motivo"] is None


def test_los_parametros_cambian_la_cuenta(admin_client, escenario):
    # Horizonte de 1 + 1 días: la necesidad (2) queda muy por debajo de lo que hay; manda el mínimo: 30 - 13 - 4.
    m = _reposicion(admin_client, dias_cobertura=1, plazo_entrega_dias=1)
    (p,) = m["productos"]
    assert p["sugerido"] == 13 and p["motivo"] == "bajo_minimo"


def test_la_sucursal_por_parametro_filtra_stock_ventas_y_lo_que_viene(admin_client, escenario):
    # La sucursal donde está la mercadería ve lo mismo, e informa que la orden no dice a qué sucursal va.
    (p,) = _reposicion(admin_client, sucursal_id=escenario["sucursal"])["productos"]
    assert (p["stock"], p["unidades_vendidas"], p["en_camino"], p["en_camino_sin_sucursal"]) == (13.0, 7.0, 4.0, 4.0)
    assert p["sugerido"] == 13
    # La otra sucursal no tiene stock ni ventas: sólo pide lo que falta para el mínimo, descontando lo que viene sin sucursal.
    m = _reposicion(admin_client, sucursal_id=escenario["otra_sucursal"])
    by_id = {p["producto_id"]: p for p in m["productos"]}
    yerba = by_id[escenario["yerba"]]
    assert (yerba["stock"], yerba["unidades_vendidas"], yerba["sin_ventas"]) == (0.0, 0.0, True)
    assert yerba["sugerido"] == 26 and yerba["motivo"] == "bajo_minimo"
    assert m["sucursal_id"] == escenario["otra_sucursal"]


def test_la_categoria_filtra(admin_client, escenario):
    assert [p["producto_id"] for p in _reposicion(admin_client, categoria="Almacén")["productos"]] == [escenario["yerba"]]
    assert _reposicion(admin_client, categoria="Bebidas")["productos"] == []


def test_un_parametro_invalido_o_una_sucursal_que_no_existe_es_422(admin_client, escenario):
    for params in ({"dias_rotacion": 0}, {"dias_cobertura": 366}, {"plazo_entrega_dias": "x"}, {"sucursal_id": 999999}):
        for ruta in RUTAS:
            assert admin_client.get(ruta, params=params).status_code == 422, (ruta, params)


def test_export_csv_bajo_el_mismo_prefijo(gerencia, escenario):
    r = gerencia.get("/api/reportes/reposicion/export")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lineas = r.text.splitlines()
    assert lineas[0].startswith("producto_id,codigo,nombre,")
    assert lineas[1].startswith(f"{escenario['yerba']},YERBA-1,Yerba 1kg,")


@pytest.mark.parametrize("rol", ROLES_SIN_ACCESO)
def test_staff_vendedor_y_cajero_no_la_ven(admin_client, escenario, rol):
    cliente = _entrar(admin_client, rol)
    for ruta in RUTAS:
        r = cliente.get(ruta)
        assert r.status_code == 403 and r.json()["detail"] == "forbidden", (rol, ruta, r.text)


def test_el_deposito_la_ve_sin_costos(admin_client, escenario):
    """ADR-054: reponer es trabajo del depósito. La respuesta no trae costos ni importes de compra."""
    cliente = _entrar(admin_client, "deposito")
    for ruta in RUTAS:
        r = cliente.get(ruta)
        assert r.status_code == 200, (ruta, r.text)
        assert "costo" not in r.text.lower(), ruta


def test_un_anonimo_no_la_ve(admin_client, escenario):
    anonimo = https_client(admin_client.app)
    for ruta in RUTAS:
        assert anonimo.get(ruta).status_code == 401, ruta


def test_la_reposicion_esta_libre_en_todos_los_planes(admin_client, escenario):
    """ADR-048: Básico y Premium se distinguen por facturación y multisucursal; no hay `require_module` sobre esta ruta."""
    for modulo in ("facturacion", "multisucursal"):
        admin_client.app.state.modules.set_enabled(modulo, False)
    assert admin_client.get("/api/reportes/reposicion").status_code == 200
    assert admin_client.get("/api/reportes/reposicion/export").status_code == 200


def test_la_reposicion_no_revela_costos(gerencia, escenario):
    """El admin y el encargado SÍ tienen `costos.ver`, así que `SinCostos` (`app/costos.py`) no les saca nada: lo que se prueba
    es que el endpoint mismo no manda ningún costo (ni por la clave, ni por el valor, ni el de la orden de compra)."""
    def claves(valor, ruta=""):
        if isinstance(valor, dict):
            for k, v in valor.items():
                if re.search(r"cost|margen|margin|subtotal", k, re.I):
                    yield f"{ruta}/{k}"
                yield from claves(v, f"{ruta}/{k}")
        elif isinstance(valor, list):
            for v in valor:
                yield from claves(v, ruta)

    for params in ({}, {"solo_a_pedir": "false"}, {"sucursal_id": escenario["sucursal"]}):
        r = gerencia.get("/api/reportes/reposicion", params=params)
        assert r.status_code == 200
        assert not list(claves(r.json())), list(claves(r.json()))
        assert COSTO not in r.text and "543.21" not in r.text and "400.00" not in r.text
        csv = gerencia.get("/api/reportes/reposicion/export", params=params)
        assert not re.search(r"cost|margen|margin", csv.text.splitlines()[0], re.I)
        assert COSTO not in csv.text and "543.21" not in csv.text


def test_lo_que_la_pantalla_del_kit_pide_al_abrir_lo_leen_el_admin_y_el_encargado(gerencia, escenario):
    """`libra-ui/comercio/Reposicion` pide `/api/sucursales` (`{id, nombre}`) y `/api/productos/categorias` (`{id, nombre}`)
    para armar sus filtros; si fallan la pantalla sigue, pero sin ese filtro. Los dos son `catalogo.ver`."""
    sucursales = gerencia.get("/api/sucursales")
    assert sucursales.status_code == 200, sucursales.text
    assert {s["nombre"] for s in sucursales.json()} >= {"Sucursal Norte"}
    assert all({"id", "nombre"} <= set(s) for s in sucursales.json())
    categorias = gerencia.get("/api/productos/categorias")
    assert categorias.status_code == 200, categorias.text
    assert [c["nombre"] for c in categorias.json()] == ["Almacén"] and all({"id", "nombre"} <= set(c) for c in categorias.json())


# ── Plazo de entrega y stock máximo por producto (ADR-055) ───────────────


def _parametros(cliente, producto_id, **cuerpo):
    return cliente.put(f"/api/productos/{producto_id}/reposicion", json=cuerpo)


def test_el_encargado_y_el_admin_cargan_el_plazo_y_el_techo_y_la_reposicion_los_usa(gerencia, escenario):
    yerba = escenario["yerba"]
    # Con 60 días de cobertura la necesidad es de 63 − 17 = 46 (rota 1 por día; 13 en stock y 4 en camino).
    assert _reposicion(gerencia, dias_cobertura=60)["productos"][0]["sugerido"] == 46
    r = _parametros(gerencia, yerba, plazo_entrega_dias=10, stock_maximo=30)   # el mínimo es 30: el techo no puede ser menor
    assert r.status_code == 200, r.text
    assert r.json()["plazo_entrega_dias"] == 10 and r.json()["stock_maximo"] == 30
    assert gerencia.get(f"/api/productos/{yerba}/reposicion").json()["stock_maximo"] == 30
    (p,) = _reposicion(gerencia, dias_cobertura=60)["productos"]
    # El plazo propio (10 en vez de 3) alarga el horizonte (70 días: 70 − 17 = 53) y el techo lo recorta: caben 30 − 17 = 13.
    assert p["sugerido"] == 13 and p["limitado_por_maximo"] is True and p["plazo_entrega_dias"] == 10 and p["plazo_propio"] is True
    # Borrar los dos vuelve a la cuenta de siempre.
    assert _parametros(gerencia, yerba, plazo_entrega_dias=None, stock_maximo=None).status_code == 200
    (p,) = _reposicion(gerencia, dias_cobertura=60)["productos"]
    assert p["sugerido"] == 46 and p["limitado_por_maximo"] is False and p["plazo_propio"] is False


def test_un_techo_menor_que_el_minimo_o_un_plazo_invalido_es_422_y_no_escribe(admin_client, escenario):
    yerba = escenario["yerba"]
    assert _parametros(admin_client, yerba, plazo_entrega_dias=3, stock_maximo=5).status_code == 422   # el mínimo es 30
    assert _parametros(admin_client, yerba, plazo_entrega_dias=0, stock_maximo=None).status_code == 422
    assert _parametros(admin_client, 999999, plazo_entrega_dias=3, stock_maximo=None).status_code == 404
    assert admin_client.get(f"/api/productos/{yerba}/reposicion").json()["plazo_entrega_dias"] is None


@pytest.mark.parametrize("rol", ["cajero", "vendedor"])
def test_los_demas_roles_no_leen_ni_escriben_los_parametros(admin_client, escenario, rol):
    cliente = _entrar(admin_client, rol)
    yerba = escenario["yerba"]
    assert cliente.get(f"/api/productos/{yerba}/reposicion").status_code == 403
    assert _parametros(cliente, yerba, plazo_entrega_dias=3, stock_maximo=None).status_code == 403
    assert admin_client.get(f"/api/productos/{yerba}/reposicion").json()["plazo_entrega_dias"] is None


def test_el_deposito_lee_y_escribe_los_parametros_pero_no_edita_el_producto(admin_client, escenario):
    """Decisión del humano (2026-10-02): reponer es trabajo del depósito. Puede cargar el plazo y el techo; el resto del producto
    (`productos.escribir`) sigue siendo del encargado y el staff."""
    deposito = _entrar(admin_client, "deposito")
    yerba = escenario["yerba"]
    r = _parametros(deposito, yerba, plazo_entrega_dias=5, stock_maximo=35)
    assert r.status_code == 200, r.text
    assert deposito.get(f"/api/productos/{yerba}/reposicion").json()["stock_maximo"] == 35
    cuerpo = {"nombre": "Yerba 1kg", "unidad": "u", "codigo": "YERBA-1", "precio_venta": PRECIO, "precio_costo": COSTO, "stock_minimo": 30}
    assert deposito.put(f"/api/productos/{yerba}", json=cuerpo).status_code == 403
    # Tampoco puede esquivar la regla del motor: un techo menor que el mínimo es 422 para él también.
    assert _parametros(deposito, yerba, plazo_entrega_dias=None, stock_maximo=10).status_code == 422


def test_sin_sesion_los_parametros_no_se_ven(admin_client, escenario):
    from fastapi.testclient import TestClient

    anonimo = TestClient(admin_client.app)
    assert anonimo.get(f"/api/productos/{escenario['yerba']}/reposicion").status_code == 401


def test_editar_el_producto_no_deja_subir_el_minimo_por_encima_del_techo_ni_para_el_staff(admin_client, escenario):
    yerba = escenario["yerba"]
    assert _parametros(admin_client, yerba, plazo_entrega_dias=None, stock_maximo=30).status_code == 200   # el mínimo es 30
    staff = _entrar(admin_client, "staff")
    cuerpo = {"nombre": "Yerba 1kg", "unidad": "u", "codigo": "YERBA-1", "precio_venta": PRECIO, "precio_costo": COSTO,
              "stock_minimo": 31}
    assert staff.put(f"/api/productos/{yerba}", json=cuerpo).status_code == 422
    assert next(p for p in admin_client.get("/api/productos").json() if p["id"] == yerba)["stock_minimo"] == 30


# ── Proveedor habitual por producto (ADR-056) ────────────────────────────


def _nuevo_proveedor(cliente, nombre):
    r = cliente.post("/api/proveedores", json={"nombre": nombre})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_el_encargado_y_el_admin_cargan_el_proveedor_y_la_reposicion_lo_muestra_y_filtra(gerencia, escenario):
    yerba = escenario["yerba"]
    norte, sur = _nuevo_proveedor(gerencia, "Distribuidora Norte"), _nuevo_proveedor(gerencia, "Mayorista Sur")
    r = _parametros(gerencia, yerba, plazo_entrega_dias=None, stock_maximo=None, proveedor_id=norte)
    assert r.status_code == 200, r.text
    assert r.json()["proveedor_id"] == norte and r.json()["proveedor"] == "Distribuidora Norte"
    (p,) = _reposicion(gerencia)["productos"]
    assert p["proveedor_id"] == norte and p["proveedor"] == "Distribuidora Norte"
    assert [x["producto_id"] for x in _reposicion(gerencia, proveedor_id=norte)["productos"]] == [yerba]
    assert _reposicion(gerencia, proveedor_id=sur)["productos"] == []
    # El CSV lo trae.
    csv = gerencia.get("/api/reportes/reposicion/export", params={"proveedor_id": norte}).text.splitlines()
    assert csv[0].endswith(",proveedor_id,proveedor") and csv[1].endswith(f",{norte},Distribuidora Norte")
    # Sin mandar la clave el proveedor queda; con null se borra.
    assert _parametros(gerencia, yerba, plazo_entrega_dias=9, stock_maximo=None).json()["proveedor_id"] == norte
    assert _parametros(gerencia, yerba, plazo_entrega_dias=9, stock_maximo=None, proveedor_id=None).json()["proveedor_id"] is None


def test_un_proveedor_que_no_existe_es_404_y_no_escribe(admin_client, escenario):
    """El gancho de VentaLibra (`party_de_proveedor`) dice 404 para un proveedor que no existe, igual que en Compras."""
    yerba = escenario["yerba"]
    assert _parametros(admin_client, yerba, plazo_entrega_dias=4, stock_maximo=None, proveedor_id=999999).status_code == 404
    assert admin_client.get(f"/api/productos/{yerba}/reposicion").json()["plazo_entrega_dias"] is None
    assert admin_client.get("/api/reportes/reposicion", params={"proveedor_id": 999999}).status_code == 404


def test_el_deposito_carga_el_proveedor_y_lista_los_proveedores_para_elegirlo(admin_client, escenario):
    """El depósito decide la reposición (`reposicion.parametros`) y puede listar proveedores (`GET /api/proveedores` es de la mercadería),
    así que el selector del formulario le sirve; no los administra."""
    deposito = _entrar(admin_client, "deposito")
    norte = _nuevo_proveedor(admin_client, "Distribuidora Norte")
    assert norte in [x["id"] for x in deposito.get("/api/proveedores").json()]
    r = _parametros(deposito, escenario["yerba"], plazo_entrega_dias=None, stock_maximo=None, proveedor_id=norte)
    assert r.status_code == 200 and r.json()["proveedor"] == "Distribuidora Norte"
    assert deposito.post("/api/proveedores", json={"nombre": "Colado"}).status_code == 403


def test_no_se_puede_eliminar_un_proveedor_que_es_el_habitual_de_un_producto(admin_client, escenario):
    yerba = escenario["yerba"]
    norte = _nuevo_proveedor(admin_client, "Distribuidora Norte")
    assert _parametros(admin_client, yerba, plazo_entrega_dias=None, stock_maximo=None, proveedor_id=norte).status_code == 200
    r = admin_client.delete(f"/api/proveedores/{norte}")
    assert r.status_code == 409 and "habitual" in r.json()["detail"]
    assert admin_client.get(f"/api/productos/{yerba}/reposicion").json()["proveedor"] == "Distribuidora Norte"
    # Soltándolo, se puede eliminar.
    assert _parametros(admin_client, yerba, plazo_entrega_dias=None, stock_maximo=None, proveedor_id=None).status_code == 200
    assert admin_client.delete(f"/api/proveedores/{norte}").status_code == 200



# ── Órdenes de compra en borrador desde la reposición (ADR-057) ──────────


def _ordenes(cliente, **cuerpo):
    cuerpo.setdefault("clave_operacion", "intento-1")
    return cliente.post("/api/reportes/reposicion/ordenes", json=cuerpo)


def test_el_encargado_y_el_admin_generan_la_orden_en_borrador_del_proveedor_habitual(gerencia, escenario):
    yerba = escenario["yerba"]
    norte = _nuevo_proveedor(gerencia, "Distribuidora Norte")
    assert _parametros(gerencia, yerba, plazo_entrega_dias=None, stock_maximo=None, proveedor_id=norte).status_code == 200
    r = _ordenes(gerencia)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    (orden,) = cuerpo["ordenes"]
    assert cuerpo["repetida"] is False and cuerpo["sin_proveedor"] == [] and orden["status"] == "draft"
    assert orden["proveedor_id"] == norte and orden["proveedor"] == "Distribuidora Norte"
    assert orden["number"].startswith("OC-")                                           # la numeración de VentaLibra, no la del motor
    (linea,) = orden["lineas"]
    # Yerba: 13 a pedir (ver `test_admin_y_encargado_ven_que_pedir_con_datos_reales`), al costo vigente del producto.
    assert (linea["nombre"], float(linea["cantidad"]), float(linea["costo_unitario"])) == ("Yerba 1kg", 13.0, float(COSTO))
    # Está en Compras como borrador, a nombre del proveedor y de quien la generó; y ya cuenta como «en camino».
    guardada = gerencia.get(f"/api/purchase-orders/{orden['id']}").json()
    assert guardada["status"] == "draft" and guardada["proveedor_id"] == norte
    (p,) = _reposicion(gerencia, solo_a_pedir="false", proveedor_id=norte)["productos"]
    assert p["en_camino"] == 4 + 13 and p["sugerido"] == 0


def test_generar_de_nuevo_con_otra_clave_no_duplica_y_con_la_misma_devuelve_lo_mismo(admin_client, escenario):
    yerba = escenario["yerba"]
    norte = _nuevo_proveedor(admin_client, "Distribuidora Norte")
    _parametros(admin_client, yerba, plazo_entrega_dias=None, stock_maximo=None, proveedor_id=norte)
    primera = _ordenes(admin_client, clave_operacion="a").json()
    mismo = _ordenes(admin_client, clave_operacion="a").json()
    assert mismo["repetida"] is True and [o["id"] for o in mismo["ordenes"]] == [o["id"] for o in primera["ordenes"]]
    otra = _ordenes(admin_client, clave_operacion="b").json()
    assert otra["ordenes"] == [] and otra["repetida"] is False
    assert len(admin_client.get("/api/purchase-orders").json()) == 2                       # la del escenario y la generada
    assert _ordenes(admin_client, clave_operacion="a", dias_cobertura=20).status_code == 409   # la misma clave con otros datos


def test_un_producto_sin_proveedor_habitual_se_informa_y_no_genera_ninguna_orden(admin_client, escenario):
    r = _ordenes(admin_client).json()
    assert r["ordenes"] == [] and [x["producto_id"] for x in r["sin_proveedor"]] == [escenario["yerba"]]
    assert len(admin_client.get("/api/purchase-orders").json()) == 1                      # sólo la del escenario


@pytest.mark.parametrize("rol", ["cajero", "vendedor", "deposito", "staff"])
def test_los_demas_roles_no_generan_ordenes(admin_client, escenario, rol):
    """Escribe órdenes de compra y trae costos: pide `reposicion.ver` y `compras.escribir` (el depósito ve la reposición pero no escribe Compras; el staff
    escribe Compras pero no ve la reposición)."""
    cliente = _entrar(admin_client, rol)
    assert _ordenes(cliente).status_code == 403
    assert len(admin_client.get("/api/purchase-orders").json()) == 1


def test_sin_sesion_no_se_generan_ordenes(admin_client, escenario):
    from fastapi.testclient import TestClient

    assert _ordenes(TestClient(admin_client.app)).status_code == 401


def test_el_cuerpo_invalido_es_422_y_un_proveedor_que_no_existe_es_404(admin_client, escenario):
    assert admin_client.post("/api/reportes/reposicion/ordenes", json={}).status_code == 422
    assert _ordenes(admin_client, dias_rotacion=0).status_code == 422
    assert _ordenes(admin_client, proveedor_id=999999).status_code == 404
    assert len(admin_client.get("/api/purchase-orders").json()) == 1
