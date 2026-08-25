#!/usr/bin/env python3
"""
Onboarding de nuevo cliente VentaLibra.
Uso: python3 scripts/nuevo_cliente.py

Wrapper de configuración sobre libracore.provisioning.nuevo_cliente (lógica
compartida con Contalibra/Restolibra/Gestiolibra/MedLibra — ver
wiki/entities/libracore.md). Solo fija las constantes propias de
VentaLibra; la lógica real vive en LibraCore.
"""
from pathlib import Path

from libracore.provisioning import configure
from libracore.provisioning.nuevo_cliente import (
    ClienteError, ask, build_image, crear_cliente, image_exists, main,
    network_exists, next_port, slugify, used_ports,
)

REPO_ROOT = Path(__file__).parent.parent.resolve()

configure(
    postgres=True,
    # ⚠️ **Tiene que decir lo mismo que `scripts/panel_admin.py`.** Hasta el
    # 2026-08-24 este archivo no pasaba `backup_zip` y el otro sí. Como pisan un
    # `_cfg` GLOBAL y `libracore.admin.services` importa los dos módulos en el
    # mismo proceso, una diferencia acá hace que el resultado dependa del orden
    # de los imports. `tests/test_provisioning.py` lo compara entero con
    # `asdict`.
    #
    # **No estaba mordiendo**: todo camino que hoy lee `cfg.backup_zip` entra por
    # `panel_admin.py`, que ya lo tenía en `True`. Se ve en el servidor — las
    # instancias vienen armando su ZIP diario en `data/backups/`. Era una mina,
    # no un incendio.
    #
    # `True` es el valor correcto y no un empate arbitrario: este producto sirve
    # su pantalla de Backups con el `build_backup_router` de `libracore.respaldo`,
    # así que el ZIP del cron es exactamente el que el cliente puede listar,
    # bajar y restaurar solo. Sin el flag, el `tar.gz` empaqueta `data/` mientras
    # el dump de PostgreSQL queda **afuera**.
    backup_zip=True,
    product_name="VENTALIBRA",
    image_name="ventalibra:latest",
    container_prefix="ventalibra",
    db_filename="ventalibra.db",
    # 🔑 **DOS cadenas, y el orden no es decorativo.** Tiene que decir lo MISMO
    # que el otro script de `scripts/` y que el `command:` de dev del compose;
    # hay un test que ata las tres puntas.
    #
    # 1. `libracore-migrar` — el schema de LibraCore, que hasta el 2026-08-25
    #    **no lo corría nadie**: sus migraciones no viajaban en el wheel. Medido
    #    ese día: de las instancias de este producto, la de dev estaba en `0002`
    #    y las otras en `0001_baseline` o **sin `alembic_version` ninguna**.
    #
    #    Resuelve la base por `VENTALIBRA_LIBRACORE_DB_PATH`, que este producto
    #    SÍ declara — aunque medido apunta a la **misma** base que
    #    `VENTALIBRA_DB_PATH`, porque acá el schema del core y el del dominio
    #    conviven. O sea que la variable existe y no hace falta la caída al
    #    dominio; ver `libracore.migrar.url_de_core`.
    #
    # 2. `alembic` — la cadena **propia**, agregada el 2026-08-25. Gobierna las
    #    5 tablas que son sólo de este producto (`users`, `sequences`,
    #    `party_billing`, `party_roles`, `sale_mp_orders`); las demás son de los
    #    motores. Va SEGUNDA por el mismo motivo que en el resto de la familia:
    #    la cadena del motor tiene que haber dejado su schema puesto antes.
    #
    #    🔴 Y acá el orden importa **además** por la tabla de versión: las dos
    #    cadenas corren contra la MISMA base, así que la propia usa
    #    `alembic_version_ventalibra` y no `alembic_version`. Ver
    #    `migrations/env.py`.
    #
    # Son dos comandos y no un `sh -c "a && b"` para que el `[ERROR]` del deploy
    # diga **cuál de las dos** falló.
    migraciones=(
        ("libracore-migrar", "upgrade", "--prefijo", "ventalibra"),
        ("alembic", "upgrade", "head"),
    ),
    repo_root=REPO_ROOT,
    base_port=8082,
)

# Re-exportados por compatibilidad con cualquier uso directo de este módulo.
CLIENTES_DIR = REPO_ROOT / "clientes"

if __name__ == "__main__":
    main()
