# syntax=docker/dockerfile:1

# Stage separado para el frontend (React+Vite+Tailwind+shadcn, ver
# DECISIONS.md ADR-014): node no hace falta en la imagen final, solo el
# resultado del build (frontend/dist).
#
# frontend/package.json referencia libra-ui (paquete de frontend
# compartido con Gestiolibra/MedLibra, extraido 2026-07-26 -- ver
# wiki/analyses/auditoria-duplicacion-familia-libra.md) via git+https,
# mismo motivo que libracore/libracommerce en el stage de Python de mas
# abajo. Este stage node:20-slim es independiente, necesita su propia
# copia de git+openssh-client + deploy key de solo lectura
# (`id_ed25519_libra_ui` en el VPS). Mount SSH con id propio (no el
# "default" generico) -- mismo patron que Contalibra/Restolibra:
# docker_build_ssh_args() (libracore >= v0.23.0) le pasa a este id su
# propia key dedicada, sin ambiguedad de que identidad ofrece GitHub.
FROM node:20-slim AS frontend-build
WORKDIR /frontend
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/*
RUN mkdir -p -m 0700 /root/.ssh && ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=ssh,id=libra-ui,target=/tmp/ssh-libra-ui.sock \
    SSH_AUTH_SOCK=/tmp/ssh-libra-ui.sock \
    sh -c 'git config --global url."ssh://git@github.com/marianocappucci/libra-ui.git".insteadOf "https://github.com/marianocappucci/libra-ui.git" && \
           npm ci'
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends openssl git openssh-client && rm -rf /var/lib/apt/lists/*

# pyproject.toml referencia LibraCommerce/LibraCore via git+https (asi
# funciona el dev local en WSL, que no tiene identidad SSH contra GitHub
# -- ver wiki/entities/libracore.md). El build en el VPS reescribe esas
# URLs a git+ssh, cada una con su propio mount SSH con id propio
# (--mount=type=ssh,id=libracore / id=libracommerce -- mismo patron que
# Contalibra/Restolibra: docker_build_ssh_args(), libracore >= v0.25.0, le
# pasa a cada id su propia key dedicada, sin ambiguedad de que identidad
# ofrece GitHub) y las descarta con la imagen: ninguna clave queda en
# ninguna capa.
#
# `pip install .` necesita resolver AMBAS dependencias en un solo comando,
# asi que no alcanza con un SSH_AUTH_SOCK global (esa variable solo puede
# apuntar a un socket a la vez). Cada dependencia usa su propio alias de
# Host, seleccionando la identidad via `IdentityAgent` (el socket del
# mount con ese id, que ya trae una sola key) en vez de `IdentityFile` --
# mismo fix que Gestiolibra/MedLibra (ver DECISIONS.md de gestiolibra
# ADR-014 para el hallazgo original): el reenvio del agente multi-key
# `default` no era compatible con `docker_build_ssh_args()`, que monta una
# key de archivo unica por id -- y ademas `_requiere_libracommerce()`
# nunca detectaba esta dependencia (declarada en pyproject.toml, no en
# requirements.txt), asi que ni siquiera se pasaba el `--ssh
# libracommerce=...` (fix en libracore v0.25.0).
RUN mkdir -p -m 0700 /root/.ssh \
    && ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null \
    && printf 'Host github-libracore\n  HostName github.com\n  User git\n  HostKeyAlias github.com\n  IdentityAgent /tmp/ssh-libracore.sock\n  IdentitiesOnly yes\n\nHost github-libracommerce\n  HostName github.com\n  User git\n  HostKeyAlias github.com\n  IdentityAgent /tmp/ssh-libracommerce.sock\n  IdentitiesOnly yes\n' > /root/.ssh/config \
    && chmod 600 /root/.ssh/config

COPY . .
# Horneado FUERA de /app a proposito (mismo motivo que gestiolibra, ver su
# DECISIONS.md ADR-022): el docker-compose.yml de dev monta ./:/app entero
# para el --reload de Python, lo que taparia cualquier build copiado
# dentro de /app con el checkout del host (que no tiene frontend/dist, es
# un artefacto gitignoreado).
COPY --from=frontend-build /frontend/dist /opt/frontend-dist
RUN --mount=type=ssh,id=libracore,target=/tmp/ssh-libracore.sock \
    --mount=type=ssh,id=libracommerce,target=/tmp/ssh-libracommerce.sock \
    git config --global url."ssh://git@github-libracore/marianocappucci/libracore.git".insteadOf "https://github.com/marianocappucci/libracore.git" \
    && git config --global url."ssh://git@github-libracommerce/marianocappucci/libracommerce.git".insteadOf "https://github.com/marianocappucci/libracommerce.git" \
    && pip install --no-cache-dir . \
    && git config --global --unset url."ssh://git@github-libracore/marianocappucci/libracore.git".insteadOf \
    && git config --global --unset url."ssh://git@github-libracommerce/marianocappucci/libracommerce.git".insteadOf

EXPOSE 8000

CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
