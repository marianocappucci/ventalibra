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
    repo_root=REPO_ROOT,
    base_port=8082,
)

# Re-exportados por compatibilidad con cualquier uso directo de este módulo.
CLIENTES_DIR = REPO_ROOT / "clientes"

if __name__ == "__main__":
    main()
