"""El costo de la mercadería sólo lo ve quien tiene `costos.ver` (ADR-049).

La matriz aprobada dice «el vendedor y el cajero no ven costos ni márgenes; el depósito, sin plata». Los márgenes y los
reportes ya estaban cerrados por su capacidad, pero `precio_costo` (productos, stock, listas de precio) y `unit_cost` y
`subtotal` (órdenes y recepciones de compra) viajaban a todo el que leía esas rutas. Ahora `app/costos.py` los saca de la
RESPUESTA para quien no tiene la capacidad.

🔑 **Cómo se prueba, sin mirar cómo está hecho el filtro:**

- `test_ningun_get_le_muestra_un_costo_a_quien_no_tiene_costos_ver` carga datos reales (un producto con costo, una orden y
  una recepción de compra con costo, listas, ventas, turnos...) y recorre TODOS los GET que publica `openapi.json` con cada
  rol restringido. Busca el costo de dos maneras: por el nombre de la clave (`cost`/`costo` como palabra, más `subtotal`) y
  **por el valor** (números que sólo el costo tiene). Si mañana el motor lo manda bajo otra clave, o una ruta nueva queda
  fuera del prefijo del filtro, se pone rojo acá.
- El contrapeso: los roles con la capacidad (admin, encargado, staff) SÍ lo ven en las rutas de costo, y lo que reciben los
  restringidos es EXACTAMENTE lo del admin menos esas claves (no se pierde ningún otro dato).
"""
import re

import pytest
from conftest import https_client
from ventas_helpers import abrir_turno, crear_item, deposito_default, registrar_venta

from app import permisos
from app.costos import sin_costos

RESTRINGIDOS = ("vendedor", "cajero", "deposito")
CON_COSTOS = ("admin", "encargado", "staff")

#: Las claves de costo MEDIDAS en las respuestas reales (ADR-049). Escrita a mano, aparte de `app/costos.py`.
CLAVES_MEDIDAS = {"precio_costo", "unit_cost", "subtotal"}

#: Números que sólo el costo tiene (ni el precio de venta, ni las cantidades, ni un id los repite).
COSTO_DEL_PRODUCTO = "731.42"
COSTO_DE_LA_ORDEN = "543.21"
SUBTOTAL_DE_LA_ORDEN = "1629.63"  # 3 x 543.21: despejar el costo es una división
COSTO_DE_LA_RECEPCION = "612.34"
COSTO_DEL_SEGUNDO = "444.44"
VALORES_DE_COSTO = (
    COSTO_DEL_PRODUCTO, COSTO_DE_LA_ORDEN, SUBTOTAL_DE_LA_ORDEN, COSTO_DE_LA_RECEPCION, COSTO_DEL_SEGUNDO,
)

CODIGO_DE_BARRAS = "7790001112223"


def _entrar(admin_client, rol):
    usuario = f"u-{rol}"
    creado = admin_client.post("/users", json={
        "username": usuario, "name": rol.title(), "password": "clave-larga-1", "role": rol,
    })
    assert creado.status_code == 201, creado.text
    cliente = https_client(admin_client.app)
    assert cliente.post("/auth/login", json={"username": usuario, "password": "clave-larga-1"}).status_code == 200
    return cliente


@pytest.fixture
def datos(admin_client):
    """Una instancia con costos cargados por todos lados, y un usuario de cada rol."""
    c = admin_client
    c.post("/catalog/units", json={"code": "u", "name": "Unidad"})
    yerba = c.post("/api/productos", json={
        "nombre": "Yerba 1kg", "unidad": "u", "precio_venta": "1500.00", "precio_costo": COSTO_DEL_PRODUCTO,
        "codigo": CODIGO_DE_BARRAS,
    })
    assert yerba.status_code == 200, yerba.text
    yerba = yerba.json()["id"]
    assert c.post(f"/api/productos/{yerba}/variantes", json={"sku": "YER-1KG-A", "nombre": "Bolsa"}).status_code == 200
    deposito = deposito_default(c)
    assert c.post(f"/api/stock/{yerba}/ajuste", json={
        "modo": "entrada", "cantidad": 40, "deposito_id": deposito, "referencia": "carga",
    }).status_code == 200

    proveedor = c.post("/api/proveedores", json={"nombre": "Distribuidora SA"}).json()["id"]
    orden = c.post("/api/purchase-orders", json={"proveedor_id": proveedor}).json()["id"]
    linea = c.post(f"/api/purchase-orders/{orden}/items", json={
        "item_id": yerba, "quantity_ordered": "3", "unit_cost": COSTO_DE_LA_ORDEN,
    })
    assert linea.status_code == 200, linea.text
    recepcion = c.post("/api/purchase-receipts", json={"proveedor_id": proveedor, "purchase_order_id": orden}).json()["id"]
    linea = c.post(f"/api/purchase-receipts/{recepcion}/items", json={
        "item_id": yerba, "quantity": "2", "unit_cost": COSTO_DE_LA_RECEPCION,
    })
    assert linea.status_code == 200, linea.text
    # Una segunda recepción, CONFIRMADA, de otro producto: mueve stock y deja su costo en el producto.
    fideos = crear_item(c, "Fideos 500g", "900.00")
    recepcion2 = c.post("/api/purchase-receipts", json={"proveedor_id": proveedor}).json()["id"]
    assert c.post(f"/api/purchase-receipts/{recepcion2}/items", json={
        "item_id": fideos, "quantity": "6", "unit_cost": COSTO_DEL_SEGUNDO,
    }).status_code == 200
    assert c.post(f"/api/purchase-receipts/{recepcion2}/confirm", json={"deposito_id": deposito}).status_code == 200

    lista = c.post("/api/listas-precio", json={"nombre": "Mayorista"}).json()["id"]
    cliente = c.post("/api/clientes", json={"name": "Cliente Uno"}).json()["id"]
    turno = abrir_turno(c)
    venta = registrar_venta(c, yerba, cantidad="2")["id"]
    assert c.post(f"/api/turnos/{turno}/cerrar", json={"monto_declarado": 3000}).status_code == 200

    usuarios = {rol: _entrar(c, rol) for rol in ("vendedor", "cajero", "deposito", "encargado", "staff")}
    usuarios["admin"] = c
    return {
        "usuarios": usuarios, "yerba": yerba, "fideos": fideos, "proveedor": proveedor, "orden": orden,
        "recepcion": recepcion, "lista": lista, "cliente": cliente, "venta": venta, "deposito": deposito,
    }


def _claves_de_costo(valor, url="", ruta="") -> list[str]:
    """Dónde aparece una clave con pinta de costo, por el NOMBRE (independiente del filtro).

    `subtotal` sólo cuenta en las compras (allí es cantidad × costo); en una venta es un importe de venta."""
    patron = r"cost|margen|margin" + (r"|subtotal" if "/api/purchase-" in url else "")
    hallazgos = []
    if isinstance(valor, dict):
        for clave, v in valor.items():
            if re.search(patron, clave, re.I):
                hallazgos.append(f"{ruta}/{clave}")
            hallazgos += _claves_de_costo(v, url, f"{ruta}/{clave}")
    elif isinstance(valor, list):
        for v in valor:
            hallazgos += _claves_de_costo(v, url, ruta)
    return hallazgos


def _valores_de_costo(texto: str) -> list[str]:
    return [v for v in VALORES_DE_COSTO if v in texto]


def _sacar_medidas(valor):
    if isinstance(valor, dict):
        return {k: _sacar_medidas(v) for k, v in valor.items() if k not in CLAVES_MEDIDAS}
    if isinstance(valor, list):
        return [_sacar_medidas(v) for v in valor]
    return valor


# ── La capacidad ─────────────────────────────────────────────────────────────


def test_costos_ver_es_de_admin_encargado_y_el_staff_heredado_y_de_nadie_mas():
    """Escrito a mano: el vendedor y el cajero no ven costos, y el depósito no ve plata."""
    assert permisos.roles_con("costos.ver") == ("admin", "encargado", "staff")
    for rol in RESTRINGIDOS:
        assert "costos.ver" not in permisos.capacidades_de(rol), rol


def test_auth_me_no_le_promete_costos_a_los_roles_restringidos(datos):
    for rol in RESTRINGIDOS:
        assert "costos.ver" not in datos["usuarios"][rol].get("/auth/me").json()["capacidades"], rol
    for rol in CON_COSTOS:
        assert "costos.ver" in datos["usuarios"][rol].get("/auth/me").json()["capacidades"], rol


# ── Lo que ve cada uno ───────────────────────────────────────────────────────


def _urls_de_costo(d) -> list[str]:
    """Las rutas donde el costo viaja, con datos reales."""
    return [
        "/api/productos", f"/api/stock/{d['yerba']}", f"/api/listas-precio/{d['lista']}/items",
        f"/api/purchase-orders/{d['orden']}", "/api/purchase-orders",
        f"/api/purchase-receipts/{d['recepcion']}", "/api/purchase-receipts",
    ]


@pytest.mark.parametrize("rol", CON_COSTOS)
def test_quien_tiene_costos_ver_lo_sigue_viendo_todo(datos, rol):
    usuario = datos["usuarios"][rol]
    productos = usuario.get("/api/productos").json()
    yerba = next(p for p in productos if p["id"] == datos["yerba"])
    assert yerba["precio_costo"] == float(COSTO_DEL_PRODUCTO)
    assert usuario.get(f"/api/stock/{datos['yerba']}").json()["producto"]["precio_costo"] == float(COSTO_DEL_PRODUCTO)
    fila = next(f for f in usuario.get(f"/api/listas-precio/{datos['lista']}/items").json() if f["id"] == datos["yerba"])
    assert fila["precio_costo"] == float(COSTO_DEL_PRODUCTO)
    orden = usuario.get(f"/api/purchase-orders/{datos['orden']}").json()
    assert orden["items"][0]["unit_cost"] == COSTO_DE_LA_ORDEN
    assert float(orden["items"][0]["subtotal"]) == float(SUBTOTAL_DE_LA_ORDEN)
    assert usuario.get(f"/api/purchase-receipts/{datos['recepcion']}").json()["items"][0]["unit_cost"] == COSTO_DE_LA_RECEPCION
    assert usuario.get("/api/purchase-orders").json()[0]["items"][0]["unit_cost"] == COSTO_DE_LA_ORDEN


@pytest.mark.parametrize("rol", RESTRINGIDOS)
def test_sin_costos_ver_llega_lo_mismo_que_al_admin_menos_el_costo(datos, rol):
    """Lo que recibe el restringido es EXACTAMENTE la respuesta del admin sin las claves de costo: no se pierde nada más."""
    admin, usuario = datos["usuarios"]["admin"], datos["usuarios"][rol]
    comparadas = []
    for url in _urls_de_costo(datos):
        r_admin = admin.get(url)
        assert r_admin.status_code == 200, url
        assert _claves_de_costo(r_admin.json(), url), f"{url}: el admin debería ver un costo (dato de prueba)"
        r = usuario.get(url)
        if r.status_code == 403:
            continue  # una ruta que el rol no lee: el vendedor y el cajero no ven compras, el depósito no consulta precios
        assert r.status_code == 200, f"{rol} {url}: {r.status_code}"
        assert not _claves_de_costo(r.json(), url), f"{rol} {url}: {_claves_de_costo(r.json(), url)}"
        assert r.json() == _sacar_medidas(r_admin.json()), f"{rol} {url}"
        comparadas.append(url)
    # Y sí leen lo suyo: productos y stock los tres; el depósito además las compras; el mostrador las listas de precio.
    esperadas = {"/api/productos", f"/api/stock/{datos['yerba']}"}
    if rol == "deposito":
        esperadas |= {u for u in _urls_de_costo(datos) if "/api/purchase-" in u}
    else:
        esperadas.add(f"/api/listas-precio/{datos['lista']}/items")
    assert esperadas <= set(comparadas), (rol, sorted(esperadas - set(comparadas)))


def test_el_deposito_ve_las_cantidades_de_la_recepcion_sin_importes(datos):
    """Lo que el depósito necesita para recibir: qué producto, cuánto se pidió, cuánto llegó y cuánto falta."""
    deposito = datos["usuarios"]["deposito"]
    orden = deposito.get(f"/api/purchase-orders/{datos['orden']}").json()
    (linea,) = orden["items"]
    assert linea["item_id"] == datos["yerba"]
    assert [float(linea[k]) for k in ("quantity_ordered", "quantity_received", "pending_quantity")] == [3.0, 0.0, 3.0]
    assert set(linea) == {"item_id", "quantity_ordered", "quantity_received", "pending_quantity", "tax_rate"}
    recepcion = deposito.get(f"/api/purchase-receipts/{datos['recepcion']}").json()
    assert float(recepcion["items"][0]["quantity"]) == 2.0 and recepcion["items"][0]["item_id"] == datos["yerba"]
    assert recepcion["status"] == "draft" and recepcion["purchase_order_id"] == datos["orden"]


def test_el_deposito_recibe_y_ni_las_respuestas_de_escritura_le_traen_el_costo(datos):
    """La escritura sigue con sus guardas y el cuerpo del pedido no se filtra (el kit manda `unit_cost`); la RESPUESTA sí."""
    deposito = datos["usuarios"]["deposito"]
    nueva = deposito.post("/api/purchase-receipts", json={"proveedor_id": datos["proveedor"]})
    assert nueva.status_code == 200, nueva.text
    rid = nueva.json()["id"]
    linea = deposito.post(f"/api/purchase-receipts/{rid}/items", json={
        "item_id": datos["yerba"], "quantity": "5", "unit_cost": "777.77",
    })
    assert linea.status_code == 200, linea.text
    assert float(linea.json()["items"][0]["quantity"]) == 5.0 and not _claves_de_costo(linea.json(), "/api/purchase-receipts")
    confirmada = deposito.post(f"/api/purchase-receipts/{rid}/confirm", json={"deposito_id": datos["deposito"]})
    assert confirmada.status_code == 200, confirmada.text
    assert confirmada.json()["status"] == "confirmed" and not _claves_de_costo(confirmada.json(), "/api/purchase-receipts")
    # Se recibió de verdad: el costo se grabó (lo ve el admin) y el depósito no lo ve.
    yerba = datos["usuarios"]["admin"].get(f"/api/stock/{datos['yerba']}").json()
    assert yerba["producto"]["precio_costo"] == 777.77
    assert "777.77" not in deposito.get(f"/api/stock/{datos['yerba']}").text
    # Y las escrituras que no eran suyas siguen cerradas.
    assert deposito.post("/api/purchase-orders", json={"proveedor_id": datos["proveedor"]}).status_code == 403
    assert deposito.put(f"/api/productos/{datos['yerba']}", json={"nombre": "X", "precio_costo": "1"}).status_code == 403


# ── Cobertura: todos los GET, con datos reales ───────────────────────────────


def _ids(d) -> dict:
    """Parámetros de ruta con un id real; los que no están acá caen en `1` (la primera fila de cualquier tabla)."""
    return {
        "pid": d["yerba"], "producto_id": d["yerba"], "orden_id": d["orden"], "recepcion_id": d["recepcion"],
        "lista_id": d["lista"], "cliente_id": d["cliente"], "vid": d["venta"], "sale_id": d["venta"], "did": d["deposito"],
    }


#: Un valor para los parámetros de query que el esquema marca como obligatorios.
CONSULTAS = {"code": CODIGO_DE_BARRAS, "producto_id": "{yerba}"}

#: `cost` en el desafío del captcha del login es la dificultad de la prueba de trabajo, no un costo: público y sin relación.
AJENAS = {"/auth/captcha"}

#: Con efecto real aun para un GET (arma un backup): sólo el admin la puede llamar y no se le pega.
NO_EJECUTAR = {"/api/config/backup-ahora"}


def _get_de_openapi(cliente):
    esquema = cliente.get("/openapi.json").json()
    for ruta, operaciones in sorted(esquema["paths"].items()):
        if "get" in operaciones and ruta not in NO_EJECUTAR:
            yield ruta, operaciones["get"]


def _armar_url(ruta, operacion, d):
    ids = _ids(d)
    url = re.sub(r"\{([^}]+)\}", lambda m: str(ids.get(m.group(1), 1)), ruta)
    obligatorios = [p["name"] for p in operacion.get("parameters", []) if p["in"] == "query" and p.get("required")]
    if not obligatorios:
        return url
    if any(nombre not in CONSULTAS for nombre in obligatorios):
        return None
    return url + "?" + "&".join(f"{n}={CONSULTAS[n].format(yerba=d['yerba'])}" for n in obligatorios)


@pytest.mark.parametrize("rol", RESTRINGIDOS)
def test_ningun_get_le_muestra_un_costo_a_quien_no_tiene_costos_ver(datos, rol):
    """El recorrido completo: cada GET de `openapi.json`, con ids reales. Falla si en un JSON aparece una clave de costo
    (por nombre) o un valor que sólo el costo tiene (por valor)."""
    usuario = datos["usuarios"][rol]
    con_200 = []
    for ruta, operacion in _get_de_openapi(usuario):
        url = _armar_url(ruta, operacion, datos)
        if url is None:
            continue
        r = usuario.get(url)
        if r.status_code != 200:
            continue
        con_200.append(url)
        assert not _valores_de_costo(r.text), f"{rol} GET {url}: trae un valor de costo"
        if "json" in r.headers.get("content-type", "") and ruta not in AJENAS:
            assert not _claves_de_costo(r.json(), url), f"{rol} GET {url}: claves de costo {_claves_de_costo(r.json(), url)}"
    # Que el recorrido no sea vacío por un error de armado: cada rol lee decenas de rutas, y las de costo entre ellas.
    assert len(con_200) >= 12, f"{rol}: sólo {len(con_200)} GET con 200: {con_200}"
    esperadas = ["/api/productos", f"/api/stock/{datos['yerba']}"]
    if rol == "deposito":  # compras: sólo el depósito de estos tres (`compras.ver`)
        esperadas.append(f"/api/purchase-orders/{datos['orden']}")
    else:  # listas de precio: sólo el mostrador (`precios.consultar`)
        esperadas.append(f"/api/listas-precio/{datos['lista']}/items")
    assert set(esperadas) <= set(con_200), (rol, esperadas, con_200)


def test_el_recorrido_encuentra_el_costo_donde_si_debe_estar(datos):
    """El detector no está ciego: el mismo recorrido, con el admin, encuentra el costo en las rutas de costo."""
    admin = datos["usuarios"]["admin"]
    con_costo = []
    for ruta, operacion in _get_de_openapi(admin):
        url = _armar_url(ruta, operacion, datos)
        r = admin.get(url) if url else None
        if r is not None and r.status_code == 200 and "json" in r.headers.get("content-type", "") and ruta not in AJENAS \
                and _claves_de_costo(r.json(), url):
            con_costo.append(ruta)
    assert {
        "/api/productos", "/api/stock/{pid}", "/api/listas-precio/{lista_id}/items", "/api/purchase-orders",
        "/api/purchase-orders/{orden_id}", "/api/purchase-receipts", "/api/purchase-receipts/{recepcion_id}",
    } <= set(con_costo)


# ── No se saltea ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("rol", RESTRINGIDOS)
def test_no_se_saltea_por_prefijo_variantes_ni_la_barra_final(datos, rol):
    usuario = datos["usuarios"][rol]
    y = datos["yerba"]
    urls = [
        "/api/productos", "/api/productos/", "/api/productos?incluir_variantes=true", "/api/productos?q=Yerba",
        f"/api/productos/{y}/codigos", f"/api/productos/{y}/variantes", f"/api/productos/escanear?code={CODIGO_DE_BARRAS}",
        "/api/productos/escanear?code=YER-1KG-A", "/api/%70roductos", f"/api/stock/{y}", f"/api/stock/{y}/",
        f"/api/stock/{y}?deposito_id={datos['deposito']}", "/api/stock", "/api/stock/movimientos",
        f"/api/depositos/{datos['deposito']}/stock", f"/api/depositos/stock-producto/{y}",
        "/api/purchase-orders/", "/api/purchase-receipts/", f"/api/purchase-orders/{datos['orden']}/",
        f"/api/purchase-receipts/{datos['recepcion']}",
    ]
    vistas = 0
    for url in urls:
        r = usuario.get(url)  # sigue las redirecciones de la barra final
        if "/api/purchase-" in url and rol != "deposito":
            assert r.status_code == 403, f"{rol} {url}: las compras no son de este rol"
            continue
        assert r.status_code == 200, f"{rol} {url}: {r.status_code}"
        assert not _claves_de_costo(r.json(), url), f"{rol} {url}"
        assert not _valores_de_costo(r.text), f"{rol} {url}"
        vistas += 1
    assert vistas >= 16
    # Sin seguir la redirección: el 307 de la barra final no lleva cuerpo.
    redireccion = usuario.get("/api/productos/", follow_redirects=False)
    assert redireccion.status_code == 307 and not redireccion.content
    # HEAD no es una ruta de lectura alternativa: el motor no la publica, y de todos modos no lleva cuerpo.
    cabecera = usuario.head("/api/productos")
    assert cabecera.status_code == 405 and not cabecera.content
    # El escaneo devuelve el producto sin costo pero con todo lo demás.
    escaneo = usuario.get(f"/api/productos/escanear?code={CODIGO_DE_BARRAS}")
    assert escaneo.status_code == 200 and escaneo.json()["producto"]["nombre"] == "Yerba 1kg"


def test_sin_sesion_no_hay_costo_ni_respuesta(datos):
    anonimo = https_client(datos["usuarios"]["admin"].app)
    for url in ("/api/productos", f"/api/stock/{datos['yerba']}", f"/api/purchase-orders/{datos['orden']}"):
        r = anonimo.get(url)
        assert r.status_code == 401 and not _claves_de_costo(r.json(), url)


def test_cambiarle_el_rol_a_alguien_le_saca_el_costo_en_el_pedido_siguiente(datos):
    """El rol se lee de la base en cada pedido (no de la cookie): quien deja de tener la capacidad deja de ver el costo sin
    volver a entrar."""
    admin, encargado = datos["usuarios"]["admin"], datos["usuarios"]["encargado"]
    assert "precio_costo" in encargado.get("/api/productos").text
    uid = next(u["id"] for u in admin.get("/users").json() if u["username"] == "u-encargado")
    assert admin.put(f"/users/{uid}", json={"name": "E", "role": "vendedor", "active": True}).status_code == 200
    productos = encargado.get("/api/productos")
    assert productos.status_code == 200 and "precio_costo" not in productos.text


# ── El POS y las promociones no se rompen ────────────────────────────────────


@pytest.mark.parametrize("rol", ["vendedor", "cajero"])
def test_el_pos_y_las_promociones_funcionan_sin_el_costo(datos, rol):
    """El POS busca productos, pide el precio de cada línea a la lista, calcula promociones y vende: nada de eso necesita el
    costo (el costo de la venta lo toma el servidor)."""
    usuario = datos["usuarios"][rol]
    productos = usuario.get("/api/productos").json()
    yerba = next(p for p in productos if p["id"] == datos["yerba"])
    assert yerba["precio_venta"] == 1500.0 and "precio_costo" not in yerba
    assert usuario.get(f"/api/listas-precio/{datos['lista']}/precio", params={"producto_id": datos["yerba"]}).status_code == 200
    calculo = usuario.post("/api/promociones/calcular", json={"items": [
        {"producto_id": datos["yerba"], "qty": 2, "precio": 1500.0},
    ]})
    assert calculo.status_code == 200, calculo.text
    abrir_turno(usuario)
    venta = registrar_venta(usuario, datos["yerba"], cantidad="1")
    assert venta["id"]
    assert not _claves_de_costo(usuario.get(f"/api/ventas/{venta['id']}").json(), "/api/ventas")


# ── El filtro en sí ──────────────────────────────────────────────────────────


def test_sin_costos_saca_las_claves_de_costo_en_cualquier_profundidad_y_deja_lo_demas():
    entrada = {
        "id": 1, "precio_venta": 10.0, "precio_costo": 5.0, "default_cost": 4, "costo_actual": 1, "sin_costo": True,
        "unit_cost_snapshot": 3, "items": [{"item_id": 2, "unit_cost": "7", "subtotal": "21", "cantidad": 3}],
        "producto": {"nombre": "x", "anidado": [[{"costo_estimado": 1, "ok": 1}]]}, "costoso": "no es una clave de costo",
        "tax_rate": "21", "cost": 1,
    }
    assert sin_costos(entrada) == {
        "id": 1, "precio_venta": 10.0,
        "items": [{"item_id": 2, "subtotal": "21", "cantidad": 3}],
        "producto": {"nombre": "x", "anidado": [[{"ok": 1}]]}, "costoso": "no es una clave de costo", "tax_rate": "21",
    }
    # `subtotal` sólo se saca donde el prefijo lo pide (compras): en otra parte es un importe cualquiera.
    assert sin_costos(entrada, frozenset({"subtotal"}))["items"] == [{"item_id": 2, "cantidad": 3}]
    assert sin_costos([1, "a", None]) == [1, "a", None]
