"""El schema **propio** de VentaLibra: lo que no es de ningún motor.

De las 63 tablas de una instancia, **5 son sólo de este producto**: `users`,
`sequences`, `party_billing`, `party_roles` y `sale_mp_orders`. Las otras las
declaran los motores, y cada uno las mantiene por su cuenta:

| Quién | Tablas | Cómo evoluciona su schema |
|---|---|---|
| `libracore` | 33 | cadena de Alembic (`alembic_version`), vía `libracore-migrar` |
| `libracommerce` | 19 + `schema_migrations` | runner numerado propio, dentro de `init_schema()` |
| `libraauth` | 6 (`usuarios`, `auth_log`, `demo_codigos`, `password_reset_tokens`, `smtp_settings`, `aceptaciones_terminos`) | `Base.metadata.create_all()` al arrancar |
| **VentaLibra** | **las 5 de arriba** | **esta función + `migrations/versions/`** |

> ⚠️ **`modulos` es un caso aparte y por eso no está en la lista.** La declaran
> **las dos**: `init_core_schema()` de LibraCore y el `init_modules_schema()` de
> acá. Como las dos usan `CREATE TABLE IF NOT EXISTS`, la crea la que corra
> primero — y desde que existe la cadena del motor, ésa siempre corre antes. La
> función se sigue llamando igual porque además **siembra las filas**
> (`INSERT OR IGNORE` de `TODOS_LOS_MODULOS`), que es lo que este producto
> necesita y el motor no hace.

Este módulo no mueve DDL: las seis funciones siguen viviendo en `app/db.py`,
donde estaban. Lo que hace es **darles un punto de entrada único**, para que la
baseline de Alembic y `connect()` llamen exactamente a lo mismo y en el mismo
orden. Antes `connect()` las enumeraba una por una: una función nueva agregada
ahí y no en la baseline —o al revés— habría dejado las instancias nuevas y las
viejas con esquemas distintos, sin fallar.

🔴 **Desde la revisión `0001`, estas seis funciones son de sólo lectura.** Todo
cambio de schema va como revisión nueva en `migrations/versions/`, no como línea
agregada ahí: `CREATE TABLE IF NOT EXISTS` crea lo que no está y **no altera lo
que sí**, así que una columna agregada ahí llega a las instancias nuevas y deja
las viejas atrás, en silencio. Lo sostiene
`tests/test_schema_propio_congelado.py`.
"""


def init_schema_propio(conn) -> None:
    """Las tablas propias de VentaLibra, en orden. Idempotente.

    La llaman `connect()` (en cada arranque) y la baseline `0001` (en el
    deploy). El orden es el que tenía `connect()` y no es indistinto:
    `party_billing`, `party_roles` y `sale_mp_orders` tienen FK contra
    `parties`/`sales`, que son de LibraCommerce — por eso la baseline llama a
    `init_commerce_schema()` antes que a esto.
    """
    # Import local y no arriba: `app.db` importa este módulo, así que un import
    # de primer nivel cerraría el ciclo. Es el mismo patrón que usa el resto de
    # la familia para las funciones que viven en el módulo de conexión.
    from app.db import (
        init_modules_schema,
        init_mp_qr_schema,
        init_party_billing_schema,
        init_party_roles_schema,
        init_sequences_schema,
        init_users_schema,
    )

    init_users_schema(conn)
    init_sequences_schema(conn)
    init_party_billing_schema(conn)
    init_party_roles_schema(conn)
    init_modules_schema(conn)
    init_mp_qr_schema(conn)
