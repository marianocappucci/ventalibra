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
