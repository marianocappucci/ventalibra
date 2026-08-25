"""Normalizacion de la grafia de MercadoPago en la base de esta instancia.

Este POS escribio `mercado_pago`, con guion bajo, desde que existe. El resto de
la familia usa `mercadopago` pegado, que es la clave de
`libracore.medios_pago.ELEGIBLES`. Era la ultima divergencia de grafia del
vocabulario, y la unica que **no se podia arreglar con un `sed`**: cambiar el
selector sin tocar las filas ya escritas parte cada reporte en dos lineas para
la misma cosa, una por grafia.

El orden, entonces, es **primero los datos y despues la grafia**, y este modulo
es la primera mitad.

## Por que corre en cada arranque y no una sola vez

No es un `if version < N` con una tabla de control, que es la forma habitual.
Corre siempre, y con la base ya normalizada no toca ninguna fila.

La razon es la segunda mitad del trabajo: cuando `mercado_pago` salga de
`libracore.medios_pago.HISTORICOS`, `label()` va a devolver el slug crudo para
cualquier fila que la tenga. Una base restaurada desde un backup anterior a esta
version volveria a tener filas asi, y **nada la volveria a normalizar** si esto
fuera un paso unico ya marcado como aplicado. Corriendo en cada arranque, una
restauracion se arregla sola al levantar el contenedor.

El costo de que corra siempre son seis `UPDATE ... WHERE` que no matchean nada.

## Las dos bases

VentaLibra tiene **dos destinos**, que contra PostgreSQL son el mismo schema y
contra SQLite son dos archivos (`ventalibra.db` y `ventalibra_libracore.db`):

- el **dominio**, de LibraCommerce, donde vive `sale_payments`;
- el de **LibraCore**, donde viven caja, cuenta corriente, egresos y recibos.

Por eso hay dos funciones y dos puntos de enganche: `app.db.connect()` para la
primera y `app.services.billing.configure()` para la segunda. Las dos corren en
el arranque, antes de que la app conteste nada.

## Que se toca, y como se supo

La lista de abajo **no salio de leer el codigo**: salio de recorrer todas las
columnas de texto de las dos instancias reales buscando el literal. El barrido
por nombre de columna —el que uno escribe primero, `column_name LIKE '%medio%'`—
encontraba `caja_movimientos` y `cc_pagos` y **se perdia `recibos.pagos`**, que
guarda el medio adentro de un JSON en una columna que no se llama nada parecido.
Ese es el motivo de que el test de guarda escanee la base entera en vez de
chequear esta lista.
"""
import json
import sqlite3

#: La grafia vieja y la canonica. Van escritas a mano y **no salen de
#: `libracore.medios_pago.EQUIVALENTE_CANONICO`** a proposito: eso es un mapa
#: vivo, que puede cambiar, y una normalizacion de datos tiene que significar
#: siempre lo mismo. Ademas el destino de esta migracion es justamente sacar
#: `mercado_pago` de ese modulo, con lo cual la entrada va a desaparecer.
GRAFIA_VIEJA = "mercado_pago"
GRAFIA_CANONICA = "mercadopago"

#: Columnas que guardan **el medio y nada mas**. Se comparan por igualdad.
_COLUMNAS_DEL_DOMINIO = (
    ("sale_payments", "method"),
)

_COLUMNAS_DE_LIBRACORE = (
    ("caja_movimientos", "medio_pago"),
    ("cc_pagos", "medio_pago"),
    ("egresos_pagos", "medio_pago"),
    # Vacia en este producto —VentaLibra registra sus ventas en `sale_payments`,
    # no aca— pero existe en el schema de LibraCore y la comparte con
    # Contalibra y Restolibra. Entra para que la normalizacion no dependa de
    # que hoy este vacia.
    ("ventas_pagos", "medio"),
)

#: Columnas que guardan el medio **adentro de un JSON**, como texto. Se
#: reemplaza el token entrecomillado, no la columna entera.
#:
#: 🔴 `recibos.pagos` es un **snapshot** de un comprobante ya emitido, y por eso
#: merece un parrafo: reescribirlo seria inaceptable si cambiara lo que el papel
#: dice. No lo cambia. El recibo imprime `medios_pago.label(...)`, que devuelve
#: "Mercado Pago" para las dos grafias — lo que se normaliza es la clave
#: interna, no el texto emitido. El test lo verifica comparando la etiqueta
#: antes y despues, no leyendo esta nota.
_JSON_DEL_DOMINIO = ()

_JSON_DE_LIBRACORE = (
    # Lista de medios habilitados de cada caja: `["efectivo", "transferencia", ...]`.
    ("cajas", "medios_pago"),
    # Snapshot de los pagos del recibo: `[{"medio_pago": "...", ...}]`.
    ("recibos", "pagos"),
)

#: El token tal como aparece adentro del JSON. Va entrecomillado para no tocar
#: un `mercado_pago` que fuera parte de otra palabra, y **no colisiona con la
#: clave** `"medio_pago"` de los dicts de `recibos.pagos`: son cadenas
#: distintas (`medio` vs `mercado`).
_TOKEN_VIEJO = json.dumps(GRAFIA_VIEJA)
_TOKEN_CANONICO = json.dumps(GRAFIA_CANONICA)


def _tablas(conn) -> set[str]:
    """Las tablas que la base tiene de verdad.

    Se pregunta en vez de asumir porque las dos bases pueden ser la misma
    (PostgreSQL) o dos archivos distintos (SQLite): contra el archivo del
    dominio, `caja_movimientos` no existe, y un `UPDATE` contra una tabla
    inexistente **aborta la transaccion entera en PostgreSQL**, no sólo la
    sentencia.
    """
    if isinstance(conn, sqlite3.Connection):
        filas = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    else:
        filas = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema()"
        ).fetchall()
    return {fila[0] for fila in filas}


def _normalizar(conn, columnas, columnas_json) -> dict[str, int]:
    """Devuelve `{tabla.columna: filas_cambiadas}`, **sólo con lo que cambio**.

    El dict vacio es el caso normal en una base ya normalizada. Se devuelve en
    vez de loguearse para que el arranque pueda decir cuanto movio y el test
    pueda afirmarlo sin leer un log.
    """
    presentes = _tablas(conn)
    cambios: dict[str, int] = {}

    for tabla, columna in columnas:
        if tabla not in presentes:
            continue
        cur = conn.execute(
            f"UPDATE {tabla} SET {columna} = ? WHERE {columna} = ?",
            (GRAFIA_CANONICA, GRAFIA_VIEJA),
        )
        if cur.rowcount:
            cambios[f"{tabla}.{columna}"] = cur.rowcount

    for tabla, columna in columnas_json:
        if tabla not in presentes:
            continue
        cur = conn.execute(
            f"UPDATE {tabla} SET {columna} = REPLACE({columna}, ?, ?) "
            f"WHERE {columna} LIKE ?",
            (_TOKEN_VIEJO, _TOKEN_CANONICO, f"%{_TOKEN_VIEJO}%"),
        )
        if cur.rowcount:
            cambios[f"{tabla}.{columna}"] = cur.rowcount

    conn.commit()
    return cambios


def normalizar_dominio(conn) -> dict[str, int]:
    """La base de LibraCommerce: `sale_payments`."""
    return _normalizar(conn, _COLUMNAS_DEL_DOMINIO, _JSON_DEL_DOMINIO)


def normalizar_libracore(conn) -> dict[str, int]:
    """La base de LibraCore: caja, cuenta corriente, egresos y recibos."""
    return _normalizar(conn, _COLUMNAS_DE_LIBRACORE, _JSON_DE_LIBRACORE)
