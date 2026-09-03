"""
Cliente para la API REST de Nginx Proxy Manager (NPM).
Documentación NPM API: http://<npm-host>:81/api/

Config leída desde scripts/.npm_config.json (generado por npm_setup.py).

Wrapper de configuración sobre libracore.npm_api (lógica compartida con
Contalibra/Restolibra/Gestiolibra/MedLibra — ver wiki/entities/libracore.md).
"""
from pathlib import Path

from libracore.npm_api import (
    NPMClient,
    NPMError,
    client_from_config,
    configure,
    forward_host_from_config,
    le_email_from_config,
    load_config,
    save_config,
)

CONFIG_FILE = Path(__file__).parent / ".npm_config.json"
configure(config_file=CONFIG_FILE)
