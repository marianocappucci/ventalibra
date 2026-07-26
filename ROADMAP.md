# Roadmap — VentaLibra

Dirección estratégica del producto. No usar para tareas pequeñas del sprint
(ver `TASKS.md`).

## Objetivo actual

- [x] Fase 1: probar de punta a punta que VentaLibra puede componer
  LibraCore (auth) + LibraCommerce (catálogo/inventario/ventas) con un
  flujo de POS real, antes de construir el resto del alcance.
- [x] Fase 2: compras (orden/recepción con orquestación de stock).
- [x] Fase 3: caja y facturación ARCA vía LibraCore.
- [~] Fase 5: onboarding multi-cliente (planes/gating de código,
  infraestructura de deploy, dominio/SSL y frontend MVP completos; falta
  el resto del back office en el frontend y reportes).

## Fases

### Fase 1 — Auth + catálogo + inventario + POS básico (completa)

- Resultado esperado: API FastAPI con login por sesión, CRUD de
  categorías/unidades/items de catálogo, ubicaciones, movimientos de stock
  manuales, y un flujo de venta (crear → agregar líneas → confirmar) que
  descuenta stock real.
- Criterio de terminado: suite de tests contra SQLite real pasando +
  verificación manual del flujo POS completo con `uvicorn`.
- Dependencias: `libracommerce` v0.1.1 (tag cortado para esta fase),
  `libracore` v0.17.1.

### Fase 2 — Compras (completa, 2026-07-25)

- Proveedores como `Party` (rol `supplier` contextual, sin columna propia —
  `app/services/suppliers.py`/`app/routers/suppliers.py`).
- Órdenes de compra (`PurchaseOrder`/`PurchaseOrderItem`) y recepciones
  (`PurchaseReceipt`/`PurchaseReceiptItem`), con o sin orden vinculada
  (`app/services/purchasing.py`/`app/routers/purchasing.py`).
- La orquestación recepción→stock **ya no se reimplementa acá**: delega
  enteramente en `libracommerce.usecases.purchasing.confirm_purchase_receipt`
  (v0.1.2), que genera el movimiento de stock, actualiza
  `CatalogItem.default_cost` (last-cost) y sincroniza `quantity_received`/
  estado de la orden vinculada — a diferencia de las ventas en Fase 1, que
  tuvo que reimplementar esa orquestación porque LibraCommerce todavía no
  la ofrecía (ver `wiki/entities/libracommerce.md`, sección "Capa de casos
  de uso").
- 10 tests nuevos (30 en total) + smoke end-to-end real contra `uvicorn`.
- Pin de `libracommerce` actualizado a `v0.1.2` (necesario para la capa de
  casos de uso). Ver DECISIONS.md ADR-004/ADR-005 sobre los dos ajustes que
  requirió ese bump.

### Fase 3 — Caja y facturación ARCA (completa, 2026-07-25)

- Segunda base SQLite dedicada a `libracore.db` (`app/services/billing.py::configure()`,
  mismo patrón exacto que `medlibra`/`gestiolibra`): `init_core_schema`,
  `caja`, `arca_facturacion`. Path por `VENTALIBRA_LIBRACORE_DB_PATH`.
- **Clientes** (`app/services/customers.py`/`app/routers/customers.py`):
  `Party` con extensión opcional `party_billing` (`cuit`/`condicion_iva`),
  mismo patrón que `client_billing` de Gestiolibra — tabla propia con FK,
  nunca columnas agregadas al motor genérico.
- **Facturación opcional por venta** (decisión del usuario, no siempre que
  haya CUIT): `POST /sales/{id}/confirm` suma `invoice: bool = False`. Si
  `true`, factura A (Responsable Inscripto) o B (cualquier otro caso,
  incluido sin cliente → "Consumidor Final") por el total de la venta —
  sin seña/saldo, a diferencia de `invoice_appointment` de MedLibra/Gestiolibra.
- **Caja siempre** (decisión del usuario, distinta a MedLibra/Gestiolibra
  donde solo se toca si hay factura): confirmar ahora exige `medio_pago` y
  registra un movimiento de caja por cada venta cobrada, facture o no. El
  control de caja es independiente del tema fiscal.
- Un solo medio de pago por venta por ahora — `ventas_pagos` (multi-medio)
  queda para una fase posterior si hace falta.
- Config ARCA vía `app/routers/billing.py` (`GET`/`PUT /config/arca`,
  admin-only) — igual que MedLibra/Gestiolibra, certificado/clave por path
  de filesystem, sin upload propio todavía.
- Decisión resuelta: no se reusó `libracore.db.usuarios` (pregunta abierta
  desde ADR-002) — se mantuvo la tabla `users` propia, sin motivo real para
  cambiar solo porque ahora hay una segunda base SQLite disponible.
- 8 tests nuevos (39 en total, más 4 de test_sales.py ajustados por el
  nuevo campo requerido `medio_pago`) + smoke end-to-end real contra
  `uvicorn`: config ARCA → cliente Responsable Inscripto → venta con
  factura (tipo A, CAE mock de dev, split de IVA correcto) → venta sin
  factura (`factura: null`) → stock final correcto.

### Fase 4 — Extensiones de catálogo (completa, 2026-07-26)

- Productos pesables: **ya funcionaba** antes de esta fase (`Unit.
  allows_fraction`/`decimal_scale` + cantidades `Decimal`) — no era un
  gap real, verificado antes de construir nada.
- Códigos de barra (`item_codes`), listas de precio (`price_lists`/
  `item_prices`), variantes de talle/color (`item_variants`):
  construidas en LibraCommerce (pin actualizado a `v0.1.3`) y conectadas
  a VentaLibra — escaneo (`GET /catalog/items/scan`), gestión de
  variantes y precios (`/pricing`), venta de una variante puntual con
  precio resuelto por lista, stock trackeado independiente por variante.
  Verificado real de punta a punta contra `uvicorn`. 62 tests pasando.
  Ver DECISIONS.md ADR-012 y `wiki/entities/libracommerce.md` (Fase 4)
  para el detalle completo del lado de LibraCommerce.

### Fase 5 — Onboarding, planes, frontend, reportes (en curso, 2026-07-26)

- [x] Planes (Básico $20k / Estándar $35k / Premium $55k) y gating por
  módulo (`facturacion` desde Estándar; catálogo/stock/venta nunca se
  gatean) — `plans.py` + tabla `modulos` + `ModuleRepository` +
  `require_module()`, mismo patrón que GestioLibra/MedLibra. 45/45 tests.
  Ver DECISIONS.md ADR-009.
- [x] Infraestructura de deploy: `Dockerfile`/`docker-compose.yml`/
  `scripts/nuevo_cliente.py`/`panel_admin.py`/`npm_api.py`/`npm_setup.py`,
  deploy keys SSH (`libracommerce` solo lectura + `ventalibra` propia).
  Contenedor `ventalibra-dev` levantado y verificado en el VPS (puerto
  `8081`, `/health` → 200, login real). Ver DECISIONS.md ADR-010.
- [x] Dominio + SSL: `ventalibra.com.ar` tenía la delegación DNS mal
  configurada, corregida por el usuario. `dev.ventalibra.com.ar`
  provisionado en NPM con SSL (`forward_host=ventalibra-dev:8000`, mismo
  patrón que contalibra-dev/gestiolibra-dev/restolibra-dev) y verificado
  real (`/health` → 200 por HTTPS). Ver DECISIONS.md ADR-010.
- [x] Primer cliente de prueba real onboardeado vía
  `scripts/nuevo_cliente.py`: `prueba` (plan Premium, puerto `8082`,
  `prueba.ventalibra.com.ar` con SSL). En el camino se encontró y
  corrigió un bug real (no específico de este repo, latente también en
  Gestiolibra/MedLibra): `build_image()` no pasa `--ssh`, así que hacía
  falta que `ventalibra:latest` ya existiera construido aparte del
  `-dev` (que compose nombra distinto). Ver DECISIONS.md ADR-011.
- [x] ~~`scripts/nuevo_cliente.py` no captura el plan elegido~~ — **no
  era un gap real** (2026-07-26): `crear_cliente()`/`main()` ya
  preguntan y aplican el plan elegido, default `basico` (no Premium).
  Corrección documental, ver DECISIONS.md ADR-013. Gap real distinto,
  transversal a toda la familia: no hay comando para cambiar el plan de
  un cliente ya onboardeado (`libracore.provisioning.panel_admin`), sin
  atacar por ahora.
- [x] Frontend (MVP, 2026-07-26): React/Vite/Tailwind/shadcn-ui (estándar
  de la familia, mismo stack final que Gestiolibra) — login, POS de
  venta (buscar/escanear, variantes, confirmar), catálogo (unidades,
  items, códigos de barra, variantes). Verificado real de punta a punta
  contra un build de producción servido por `uvicorn`. Ver DECISIONS.md
  ADR-014. Resto del back office (compras/proveedores/clientes/config
  ARCA/usuarios/sucursales) sigue por API directa, se suma cuando se
  priorice.
- [ ] Reportes de ventas, caja y stock.
- Validar con un comercio real antes de sumar promociones avanzadas,
  multi-sucursal o modo offline (ver `wiki/analyses/arquitectura-familia-libra-alcance.md`,
  "Orden de implementación").

## Futuro

- Modo offline (mini PC local) reusando `libraedge`/la integración ya
  construida en LibraCommerce — evaluar una vez validado con un comercio real.
