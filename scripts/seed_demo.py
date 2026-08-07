#!/usr/bin/env python3
"""Carga los datos de la demo pública de VentaLibra — ítem 8 de los pendientes
transversales de Libra.

**Para qué.** Una demo vacía no muestra nada: quien entra ve pantallas en blanco
y se va. Este script deja la instancia con un almacén de barrio andando, para
que las pantallas se puedan mirar.

**Por la API y no por SQL**, a propósito: así los datos pasan por las mismas
validaciones y los mismos servicios que usa la pantalla. Un seed por SQL puede
crear estados que la aplicación nunca produciría —una venta confirmada sin
movimiento de caja, por ejemplo— y entonces lo que se muestra no es el producto.

**No cubre sólo el caso feliz.** Deja los estados que las pantallas distinguen:
ventas confirmadas y una cancelada, un ítem sin stock y otro por debajo del
mínimo, una lista de precios además de la de referencia, y un artículo que se
vende por peso — que es la razón de que este producto tenga unidades con
fracción.

**Es idempotente**: si el registro ya existe no lo duplica. El cron de reset lo
corre después de recrear la base, pero correrlo dos veces no rompe nada.

> 🔴 **Nunca contra la instancia de un cliente.** Se planta si el host no es de
> dev, demo, prueba o local — ver `url_no_productiva`.

Uso:
    python scripts/seed_demo.py --url https://demo.ventalibra.com.ar \\
        --usuario admin --password ...
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.cookiejar import CookieJar
from urllib.parse import urlparse

#: Los subdominios que NO son de un cliente. Se compara el host entero o su
#: primera etiqueta, **no como substring de la URL**: con substrings, un cliente
#: llamado `demoliciones.ventalibra.com.ar` pasaría la guarda.
_HOSTS_NO_PRODUCTIVOS = ("dev", "demo", "prueba", "localhost", "127.0.0.1")


def url_no_productiva(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return host in _HOSTS_NO_PRODUCTIVOS or host.split(".")[0] in _HOSTS_NO_PRODUCTIVOS


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )

    def _pedir(self, metodo: str, ruta: str, cuerpo=None):
        datos = json.dumps(cuerpo, default=str).encode() if cuerpo is not None else None
        req = urllib.request.Request(
            f"{self.base}{ruta}", data=datos, method=metodo,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(req, timeout=30) as r:
                crudo = r.read()
                return json.loads(crudo) if crudo else None
        except urllib.error.HTTPError as e:
            detalle = e.read().decode(errors="replace")[:300]
            raise RuntimeError(f"{metodo} {ruta} -> {e.code}: {detalle}") from None

    def get(self, ruta):
        return self._pedir("GET", ruta)

    def post(self, ruta, cuerpo=None):
        return self._pedir("POST", ruta, cuerpo)

    def put(self, ruta, cuerpo=None):
        return self._pedir("PUT", ruta, cuerpo)


def _lista(datos):
    """Los listados de este producto a veces vienen envueltos
    (`{"items": [...]}`). Devuelve siempre la lista."""
    if isinstance(datos, list):
        return datos
    if isinstance(datos, dict):
        return next((v for v in datos.values() if isinstance(v, list)), [])
    return []


def obtener_o_crear(api: Api, ruta_lista: str, clave: str, valor, cuerpo: dict,
                    ruta_alta: str | None = None):
    """Crea el registro si no está. Devuelve `(registro, es_nuevo)`.

    La idempotencia va por un campo con significado —el nombre, el código— y no
    por "¿la tabla está vacía?": así el seed se puede correr después de agregar
    un ítem nuevo sin duplicar los anteriores.
    """
    lista = api.get(ruta_lista) or []
    # Algunos listados vienen envueltos (`{"items": [...]}`).
    if isinstance(lista, dict):
        lista = next((v for v in lista.values() if isinstance(v, list)), [])
    for existente in lista:
        if existente.get(clave) == valor:
            return existente, False
    return api.post(ruta_alta or ruta_lista, cuerpo), True


# ── El negocio ────────────────────────────────────────────────────────────
#
# Un almacén de barrio. Se eligió un rubro donde conviven el artículo por
# unidad y el que se vende por peso —que es lo que distingue a este producto de
# un catálogo cualquiera— y donde el stock bajo se entiende sin explicación.

UNIDADES = [
    {"code": "UN", "name": "Unidad"},
    # Con fracción: es lo que hace posible vender 0,350 kg de queso. Sin al
    # menos una así, la balanza y los decimales del ticket no se ven.
    {"code": "KG", "name": "Kilogramo", "allows_fraction": True, "decimal_scale": 3},
]

CATEGORIAS = ["Almacén", "Bebidas", "Fiambrería", "Limpieza"]

#: (nombre, unidad, categoría, precio de venta, costo)
ARTICULOS = [
    ("Yerba mate 1 kg", "UN", "Almacén", 4800, 3200),
    ("Fideos guiseros 500 g", "UN", "Almacén", 1450, 980),
    ("Arroz largo fino 1 kg", "UN", "Almacén", 1900, 1300),
    ("Aceite de girasol 1,5 L", "UN", "Almacén", 5200, 3900),
    ("Gaseosa cola 2,25 L", "UN", "Bebidas", 3600, 2500),
    ("Agua mineral 2 L", "UN", "Bebidas", 1800, 1150),
    ("Cerveza rubia 473 cc", "UN", "Bebidas", 2400, 1600),
    ("Queso cremoso", "KG", "Fiambrería", 12500, 8900),
    ("Jamón cocido", "KG", "Fiambrería", 18900, 13500),
    ("Detergente 750 ml", "UN", "Limpieza", 2700, 1850),
    ("Lavandina 1 L", "UN", "Limpieza", 1600, 1050),
]

CLIENTES = [
    {"display_name": "Consumidor final", "party_type": "person"},
    {"display_name": "Rosa Giménez", "party_type": "person", "phone": "11 4455-6677",
     "condicion_iva": "Consumidor Final"},
    {"display_name": "Kiosco La Esquina", "party_type": "organization",
     "cuit": "30-71888999-2", "condicion_iva": "Responsable Inscripto",
     "email": "laesquina@example.com.ar"},
    {"display_name": "Comedor San Cayetano", "party_type": "organization",
     "cuit": "30-71222333-4", "condicion_iva": "IVA Exento"},
]

PROVEEDORES = [
    {"display_name": "Distribuidora Sur", "legal_name": "Distribuidora Sur SRL",
     "tax_id": "30-70111222-3", "phone": "11 4300-1122"},
    {"display_name": "Lácteos del Valle", "legal_name": "Lácteos del Valle SA",
     "tax_id": "30-70444555-6", "email": "ventas@example.com.ar"},
]

DEPOSITOS = [
    {"name": "Salón", "location_type": "store"},
    {"name": "Depósito", "location_type": "warehouse"},
]

#: Stock inicial por artículo. **No todos tienen**: uno queda en cero y otro
#: bajo, porque la pantalla de stock existe justamente para mostrar eso. Con
#: todo abastecido, la mitad de esa pantalla no se ve.
STOCK = {
    "Yerba mate 1 kg": 48,
    "Fideos guiseros 500 g": 120,
    "Arroz largo fino 1 kg": 96,
    "Aceite de girasol 1,5 L": 6,      # bajo
    "Gaseosa cola 2,25 L": 72,
    "Agua mineral 2 L": 60,
    "Cerveza rubia 473 cc": 0,          # sin stock
    "Queso cremoso": 14.5,
    "Jamón cocido": 8.2,
    "Detergente 750 ml": 36,
    "Lavandina 1 L": 3,                 # bajo
}


def sembrar(api: Api) -> None:
    hechos = {}

    def contar(clave: str, nuevo: bool):
        creados, existentes = hechos.get(clave, (0, 0))
        hechos[clave] = (creados + int(nuevo), existentes + int(not nuevo))

    print("Unidades…")
    for u in UNIDADES:
        _, nuevo = obtener_o_crear(api, "/catalog/units", "code", u["code"], u)
        contar("unidades", nuevo)

    print("Categorías…")
    categorias = {}
    for nombre in CATEGORIAS:
        registro, nuevo = obtener_o_crear(
            api, "/catalog/categories", "name", nombre, {"name": nombre})
        categorias[nombre] = registro["id"]
        contar("categorías", nuevo)

    print("Artículos…")
    articulos = {}
    for nombre, unidad, categoria, precio, costo in ARTICULOS:
        registro, nuevo = obtener_o_crear(api, "/catalog/items", "name", nombre, {
            "name": nombre, "unit_code": unidad,
            "category_id": categorias[categoria],
            "default_sale_price": precio, "default_cost": costo,
        })
        articulos[nombre] = registro["id"]
        contar("artículos", nuevo)

    print("Clientes…")
    clientes = {}
    for c in CLIENTES:
        registro, nuevo = obtener_o_crear(
            api, "/customers", "display_name", c["display_name"], c)
        clientes[c["display_name"]] = registro
        contar("clientes", nuevo)

    print("Proveedores…")
    for p in PROVEEDORES:
        _, nuevo = obtener_o_crear(
            api, "/suppliers", "display_name", p["display_name"], p)
        contar("proveedores", nuevo)

    print("Depósitos…")
    depositos = {}
    for d in DEPOSITOS:
        registro, nuevo = obtener_o_crear(api, "/locations", "name", d["name"], d)
        depositos[d["name"]] = registro["id"]
        contar("depósitos", nuevo)

    print("Stock…")
    _sembrar_stock(api, articulos, depositos["Salón"], contar)

    print("Turno de caja…")
    # 🔴 **Confirmar una venta exige un turno abierto.** Sin esto, las ventas
    # quedan creadas pero sin confirmar: no descuentan stock, no mueven caja y
    # ni siquiera aparecen en el listado. Es la primera cosa que rompió al
    # escribir este seed, y es correcta — así funciona un mostrador.
    _abrir_turno(api, contar)

    print("Ventas…")
    _sembrar_ventas(api, articulos, clientes, depositos["Salón"], contar)

    print("Compras (orden y recepción)…")
    _sembrar_compras(api, articulos, depositos["Salón"], contar)

    print("Cuenta corriente…")
    _sembrar_cuenta_corriente(api, articulos, clientes, depositos["Salón"], contar)

    # El logo del negocio, para que los comprobantes salgan como los de
    # un cliente y no con un hueco arriba.
    _cargar_logo(api, "Almacén Don Aldo", "A", (217, 119, 6), contar)

    print()
    for clave, (creados, existentes) in sorted(hechos.items()):
        print(f"  {clave:<12} {creados} creados, {existentes} ya estaban")


def _abrir_turno(api: Api, contar) -> None:
    """Abre el turno de caja, si no hay uno abierto.

    El endpoint devuelve 409 si ya hay uno —no se abre uno encima de otro,
    porque el arqueo del primero quedaría partido—, así que ese 409 es el
    camino idempotente y no un error.
    """
    try:
        api.post("/shifts/open", {"monto_inicial": 20000,
                                  "notas": "Apertura de la demo"})
        contar("turno", True)
    except RuntimeError as e:
        if "409" in str(e):
            contar("turno", False)
        else:
            raise


def _sembrar_stock(api: Api, articulos: dict, deposito: int, contar) -> None:
    """El stock entra por **ajustes**, que es como lo carga una persona la
    primera vez. Un `INSERT` directo en la tabla de existencias dejaría el
    saldo sin el movimiento que lo explica, y la pantalla de movimientos
    mostraría un stock que apareció de la nada.

    Idempotente mirando la existencia actual: `/stock/adjustments` no tiene
    listado —es un movimiento, no un registro— así que la única forma de saber
    si ya se cargó es preguntarle al saldo.
    """
    for nombre, cantidad in STOCK.items():
        if cantidad == 0:
            # Sin ajuste: el artículo queda en cero, que es un estado real y el
            # que la pantalla de faltantes tiene que mostrar.
            continue
        if _existencia(api, articulos[nombre], deposito) > 0:
            contar("stock", False)
            continue
        try:
            api.post("/stock/adjustments", {
                "item_id": articulos[nombre], "location_id": deposito,
                "quantity_delta": cantidad, "reason": "Carga inicial",
            })
            contar("stock", True)
        except RuntimeError as e:
            print(f"  -- {nombre}: {e}")


def _existencia(api: Api, item_id: int, location_id: int) -> float:
    """El saldo actual de un artículo en un depósito.

    ⚠️ Dos cosas que no se adivinan: la ruta es `/stock/{item_id}` —**no**
    `/stock/items/{item_id}`, que da 404— y `location_id` es un query param
    **obligatorio**. El stock es por depósito, no un número global, y pedirlo
    sin decir dónde no tendría respuesta.
    """
    datos = api.get(f"/stock/{item_id}?location_id={location_id}")
    if datos is None:
        return 0.0
    if isinstance(datos, list):
        return sum(float(e.get("quantity", 0)) for e in datos)
    for clave in ("quantity", "total", "cantidad"):
        if clave in datos:
            return float(datos[clave] or 0)
    filas = next((v for v in datos.values() if isinstance(v, list)), [])
    return sum(float(e.get("quantity", 0)) for e in filas)


def _sembrar_ventas(api: Api, articulos: dict, clientes: dict,
                    deposito: int, contar) -> None:
    """Ventas confirmadas y una cancelada.

    Cada venta se arma con el mismo recorrido que hace el mostrador: crear,
    agregar líneas, confirmar con el pago. Confirmar es lo que descuenta stock
    y mueve la caja — armarlas por SQL dejaría ventas sin ninguna de las dos
    cosas.
    """
    existentes = api.get("/sales") or []
    if isinstance(existentes, dict):
        existentes = next((v for v in existentes.values() if isinstance(v, list)), [])
    if len(existentes) >= 4:
        contar("ventas", False)
        print(f"  (ya hay {len(existentes)} ventas)")
        return

    PLAN = [
        # (cliente, [(artículo, cantidad)], medio de pago, cancelar)
        ("Consumidor final",
         [("Yerba mate 1 kg", 1), ("Fideos guiseros 500 g", 2)], "efectivo", False),
        ("Rosa Giménez",
         [("Queso cremoso", 0.35), ("Jamón cocido", 0.25),
          ("Agua mineral 2 L", 2)], "debito", False),
        ("Kiosco La Esquina",
         [("Gaseosa cola 2,25 L", 12), ("Detergente 750 ml", 6)], "transferencia", False),
        ("Consumidor final",
         [("Arroz largo fino 1 kg", 3)], "efectivo", False),
        # Cancelada: la pantalla de ventas la distingue, y sin ninguna esa
        # columna se ve siempre igual.
        ("Consumidor final",
         [("Lavandina 1 L", 1)], "efectivo", True),
        # 🔴 Fiada: es la ÚNICA forma de que exista una cuenta corriente. Sin
        # esta venta, las pantallas de cuenta corriente y recibos quedan
        # vacías — no hay endpoint para crear una deuda de la nada, y está
        # bien que no lo haya: la deuda nace de una venta.
        ("Kiosco La Esquina",
         [("Yerba mate 1 kg", 4), ("Gaseosa cola 2,25 L", 6)],
         "cuenta_corriente", False),
    ]

    for cliente, lineas, medio, cancelar in PLAN:
        try:
            venta = api.post("/sales", {
                "customer_party_id": clientes[cliente].get("party_id")
                or clientes[cliente].get("id"),
            })
            for articulo, cantidad in lineas:
                venta = api.post(f"/sales/{venta['id']}/items", {
                    "item_id": articulos[articulo], "quantity": cantidad,
                })
            total = venta.get("total") or venta.get("total_amount") or 0
            venta = api.post(f"/sales/{venta['id']}/confirm", {
                "pagos": [{"medio": medio, "monto": total,
                           "recibido": total if medio == "efectivo" else None}],
                "location_id": deposito,
            })
            contar("ventas", True)
            if cancelar:
                api.post(f"/sales/{venta['id']}/cancel", {})
        except RuntimeError as e:
            print(f"  -- venta de {cliente}: {e}")


def _sembrar_compras(api: Api, articulos: dict, deposito: int, contar) -> None:
    """Una orden de compra y su recepción, con el mismo recorrido que hace el
    encargado: crear la orden, agregarle líneas, recibir contra esa orden y
    confirmar.

    Las dos pantallas estaban vacías. Y la recepción **confirmada** es lo que
    de verdad interesa mostrar: es la que entra la mercadería al stock, así que
    sin confirmar se vería una recepción que no movió nada.
    """
    if _lista(api.get("/purchase-orders")):
        contar("compras", False)
        print("  (ya hay órdenes de compra)")
        return

    proveedores = _lista(api.get("/suppliers"))
    if not proveedores:
        print("  -- sin proveedores, no se puede armar la compra")
        return
    proveedor = proveedores[0]
    # El id de la orden es el del **party**, no el del proveedor: son dos
    # entidades distintas en este producto.
    party = proveedor.get("party_id") or proveedor.get("id")

    LINEAS = [("Yerba mate 1 kg", 24, 3200), ("Arroz largo fino 1 kg", 40, 1150)]
    try:
        orden = api.post("/purchase-orders", {"supplier_party_id": party})
        for nombre, cantidad, costo in LINEAS:
            if nombre not in articulos:
                continue
            api.post(f"/purchase-orders/{orden['id']}/items", {
                "item_id": articulos[nombre], "quantity_ordered": cantidad,
                "unit_cost": costo, "tax_rate": 0.21,
            })
        contar("orden_compra", True)

        recepcion = api.post("/purchase-receipts", {
            "supplier_party_id": party, "purchase_order_id": orden["id"],
            "document_reference": "Remito 0001-00004512",
        })
        for nombre, cantidad, costo in LINEAS:
            if nombre not in articulos:
                continue
            api.post(f"/purchase-receipts/{recepcion['id']}/items", {
                "item_id": articulos[nombre], "quantity": cantidad,
                "unit_cost": costo,
            })
        # 🔴 Confirmar pide **a qué depósito entra** la mercadería, y con razón:
        # es lo que decide dónde suma el stock. Sin `location_id` contesta 422.
        api.post(f"/purchase-receipts/{recepcion['id']}/confirm",
                 {"location_id": deposito})
        contar("recepcion", True)
    except RuntimeError as e:
        print(f"  -- compras: {e}")


def _sembrar_cuenta_corriente(api: Api, articulos: dict, clientes: dict,
                              deposito: int, contar) -> None:
    """Un cliente con saldo y una cobranza parcial.

    🔴 **Cobrar exige turno de caja abierto** —es plata que entra y tiene que
    aparecer en el arqueo—, así que esto va después de `_abrir_turno`. Sin
    turno el endpoint contesta 409, que es correcto y no un error a esquivar.

    La cobranza además emite su **recibo**: es la otra pantalla que quedaba
    vacía, y el papel que el cliente se lleva.
    """
    cuentas = _lista(api.get("/accounts"))
    # La guarda va por "ya cobre?", no por "hay saldo?". Escrita al reves
    # salteaba justamente el caso en el que hay que cobrar, y la pantalla de
    # recibos quedaba vacia con la cuenta cargada.
    if not cuentas:
        print("  -- sin cuentas: la venta fiada no se confirmo")
        return
    _c = cuentas[0]
    _party = _c.get("party_id") or _c.get("id")
    if any(m.get("cc_pago_id") for m in _lista(api.get(f"/accounts/{_party}"))):
        contar("cobranza", False)
        print("  (ya hay una cobranza)")
        return

    # El fiado nace de la venta a cuenta corriente del plan de ventas. Si no
    # hay ninguna cuenta, es que esa venta no llegó a confirmarse.
    if not cuentas:
        print("  -- sin cuentas: la venta fiada no se confirmó")
        return
    cuenta = cuentas[0]
    party = cuenta.get("party_id") or cuenta.get("id")
    try:
        api.post(f"/accounts/{party}/payments", {
            "monto": 5000, "medio_pago": "efectivo",
            "concepto": "Pago a cuenta", "referencia": "Recibo de la demo",
        })
        contar("cobranza", True)
    except RuntimeError as e:
        print(f"  -- cobranza: {e}")



def _cargar_logo(api, nombre: str, inicial: str, color: tuple, contar) -> None:
    """Dibuja el logo del negocio y lo sube a Configuración.

    🔴 **Se genera, no se commitea.** PIL viene en la imagen del producto, así
    que el seed lo dibuja en el momento: no hay binarios en el repo y cambiar
    el color es cambiar una línea. Mismo criterio que el resto del seed — el
    estado limpio es código, no un archivo guardado a mano.

    Sin logo, los PDF de la demo salen con un hueco arriba: el interesado ve
    dónde iría el suyo pero no cómo se ve.

    ⚠️ El campo del multipart se llama **`logo`**, no `file`: con `file` la API
    contesta 422. Está leído del openapi de la instancia.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("  (sin PIL: se saltea el logo)")
        return

    # 🔴 La ruta de configuración no es la misma en todos los productos, y
    # pedir la que no existe **no da 404**: el catch-all de la SPA contesta
    # 200 con el index.html y el parseo revienta. Así que la guarda no puede
    # depender de acertarla: ante cualquier duda se sube el logo, que es
    # inocuo, en vez de arriesgar quedarse sin él.
    for ruta in ("/api/config/empresa", "/api/config"):
        try:
            actual = api.get(ruta)
        except Exception:
            continue
        if isinstance(actual, dict):
            plano = str(actual)
            if '"logo"' in plano or "'logo'" in plano:
                if any("logo" in str(k) and v for k, v in actual.items()):
                    contar("logo", False)
                    return
            break

    imagen = Image.new("RGBA", (520, 160), (255, 255, 255, 0))
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rounded_rectangle((8, 20, 128, 140), radius=24, fill=color)
    dibujo.text((52, 60), inicial, fill=(255, 255, 255))
    dibujo.text((150, 55), nombre, fill=(30, 30, 30))
    dibujo.line((150, 95, 150 + min(340, len(nombre) * 11), 95), fill=color, width=4)

    # 🔴 La subida es multipart a mano, así que necesita la URL y el opener del
    # `Api` real. La suite corre el seed contra un doble que habla directo con
    # la app y no tiene ninguno de los dos: sin esta guarda, `api.base`
    # reventaba con AttributeError y se llevaba puestos **11 tests** del seed
    # entero, no sólo el del logo.
    if not getattr(api, "base", None) or not getattr(api, "opener", None):
        return

    import io
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")

    limite = "----seed" + "0" * 12
    cuerpo = (
        f"--{limite}\r\n"
        'Content-Disposition: form-data; name="logo"; filename="logo.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode() + buffer.getvalue() + f"\r\n--{limite}--\r\n".encode()

    import urllib.request
    pedido = urllib.request.Request(
        f"{api.base}/api/config/empresa/logo", data=cuerpo, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={limite}"},
    )
    try:
        api.opener.open(pedido, timeout=30)
        contar("logo", True)
    except Exception as e:
        print(f"  -- logo: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--usuario", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument(
        "--force", action="store_true",
        help="Correr contra una URL que no parece de dev ni de demo. No usar.",
    )
    args = ap.parse_args()

    if not url_no_productiva(args.url) and not args.force:
        print(f"ERROR: {args.url} no parece una instancia de dev ni de demo.",
              file=sys.stderr)
        print("Este script NO se corre contra la instancia de un cliente.",
              file=sys.stderr)
        return 2

    api = Api(args.url)
    api.post("/auth/login", {"username": args.usuario, "password": args.password})
    sembrar(api)
    return 0


if __name__ == "__main__":
    sys.exit(main())
