# Tasks — VentaLibra

Trabajo concreto y vigente. Al completar o descartar una tarea, actualizarla;
no usar este archivo como historial (para eso está `CHANGELOG.md`).

## En curso

- [ ] Ninguna por ahora.

## Completadas

- [x] Scaffold Fase 1: persistencia (`app/db.py`), auth
  (`app/auth.py`/`security.py`/`services/users.py`), catálogo
  (`app/services/catalog.py`), stock, ventas POS (`app/services/sales.py`),
  routers, tests, CI — responsable: LLM.
- [x] Fase 2: compras (proveedores, orden/recepción, orquestación de stock
  vía `libracommerce.usecases.purchasing.confirm_purchase_receipt`) — pin
  de `libracommerce` a v0.1.2, secuencias propias (`app/db.py`), 10 tests
  nuevos (30 en total) + smoke end-to-end — responsable: LLM.
- [x] Fase 3: caja/facturación vía LibraCore (`app/services/billing.py`,
  segunda base SQLite dedicada, clientes con extensión `party_billing`,
  facturación opcional por venta, caja siempre al confirmar) — 8 tests
  nuevos (39 en total) + smoke end-to-end — responsable: LLM.
- [x] Fase 5 (código): planes y gating por módulo (`plans.py`, tabla
  `modulos`, `ModuleRepository`, `require_module()`) — 6 tests nuevos
  (45 en total) — responsable: LLM.
- [x] Fase 5 (infraestructura): `Dockerfile`/`docker-compose.yml`/scripts
  de onboarding, deploy keys SSH (`libracommerce`/`ventalibra`),
  contenedor `ventalibra-dev` verificado en el VPS (puerto 8081) —
  responsable: LLM.
- [x] Fase 5 (dominio/SSL): DNS de `ventalibra.com.ar` corregido por el
  usuario; NPM+SSL provisionado para `dev.ventalibra.com.ar`
  (`forward_host=ventalibra-dev:8000`), verificado real por HTTPS —
  responsable: LLM (provisioning) + usuario (fix de DNS).
- [x] Fase 5 (primer cliente real): `prueba` onboardeado vía
  `scripts/nuevo_cliente.py` (plan Premium, puerto 8082,
  `prueba.ventalibra.com.ar` con SSL). Bug real encontrado y corregido en
  el camino (`build_image()` sin `--ssh`, latente también en
  Gestiolibra/MedLibra) — ver DECISIONS.md ADR-011 — responsable: LLM.
- [x] Fase 4: códigos de barra/listas de precio/variantes construidas en
  LibraCommerce (pin `v0.1.3`) y conectadas a VentaLibra (`/catalog/
  items/scan`, `/pricing`, `variant_id` en ventas y stock) — 17 tests
  nuevos (62 en total), verificado real contra `uvicorn` — ver
  DECISIONS.md ADR-012 — responsable: LLM.
- [x] Corrección: "captura de plan en el onboarding" no era un pendiente
  real — `crear_cliente()`/`main()` ya lo hacían. Ver DECISIONS.md
  ADR-013 — responsable: LLM.
- [x] Frontend (MVP): React/Vite/Tailwind/shadcn-ui — login, POS de
  venta (buscar/escanear/variantes/confirmar), catálogo (unidades,
  items, códigos, variantes). Verificado real de punta a punta contra
  un build de producción. Ver DECISIONS.md ADR-014 — responsable: LLM.
- [x] Frontend: resto del back office (sucursales, proveedores,
  clientes, compras, usuarios, config ARCA). Bug real corregido en el
  camino (`party_roles`, mezcla de clientes/proveedores). Pin de
  `libracommerce` a `v0.1.4`. Verificado real de punta a punta,
  66/66 tests. Ver DECISIONS.md ADR-015 — responsable: LLM.
- [x] Reportes de ventas, caja y stock (admin-only, sin tabla propia).
  Verificado real de punta a punta, 74/74 tests. Ver DECISIONS.md
  ADR-016 — responsable: LLM. **Cierra Fase 5.**
- [x] Incidente: `dev.ventalibra.com.ar` caído (código viejo deployado) +
  gap de fondo (`init_schema()` no migra bases persistidas). Mecanismo
  real de migraciones en LibraCommerce (`v0.1.5`, 8 tests nuevos),
  verificado contra la base real del cliente `prueba` sin pérdida de
  datos. Ver DECISIONS.md ADR-017 — responsable: LLM.

## Próximas

- [ ] Ninguna por ahora — próximo hito de VentaLibra a definir (fuera
  de Fase 5).

## Bloqueadas

- [ ] Ninguna por ahora.
