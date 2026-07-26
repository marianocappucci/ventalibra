#!/usr/bin/env python3
"""
Configuración de la conexión a Nginx Proxy Manager.
Uso: python3 scripts/npm_setup.py

Guarda la config en scripts/.npm_config.json (excluido del repo).

Wrapper de configuración sobre libracore.npm_setup (lógica compartida con
Contalibra/Restolibra/Gestiolibra/MedLibra — ver wiki/entities/libracore.md).
"""
from pathlib import Path

from libracore.npm_api import configure as _configure_npm_api
from libracore.npm_setup import main as _main

_configure_npm_api(config_file=Path(__file__).parent / ".npm_config.json")


def main():
    _main(product_name="VENTALIBRA")


if __name__ == "__main__":
    main()
