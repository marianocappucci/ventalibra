# Roadmap — VentaLibra

Dirección estratégica del producto. No usar para tareas pequeñas del sprint
(ver `TASKS.md`).

## Objetivo actual

- [x] Fase 1: probar de punta a punta que VentaLibra puede componer
  LibraCore (auth) + LibraCommerce (catálogo/inventario/ventas) con un
  flujo de POS real, antes de construir el resto del alcance.
- [x] Fase 2: compras (orden/recepción con orquestación de stock).
- [x] Fase 3: caja y facturación ARCA vía LibraCore.
- [~] Fase 5: onboarding multi-cliente (planes/gating de código completo;
  infraestructura de deploy verificada en el VPS; falta el dominio/SSL).

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

### Fase 4 — Extensiones de catálogo (requieren tocar LibraCommerce primero)

- Códigos de barra (`item_codes`), variantes de talle/color
  (`item_variants`), listas de precio (`price_lists`/`item_prices`),
  productos pesables. Ninguno de estos existe todavía en LibraCommerce —
  son extensiones al motor compartido, no al vertical, según el propio
  análisis de arquitectura de la familia. Se decide de forma explícita
  cuando se llegue a esta fase, no de pasada.

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
- [ ] **Bloqueado**: `ventalibra.com.ar` tiene delegación DNS mal
  configurada (nameservers devuelven REFUSED) — sin esto no se puede
  provisionar NPM+SSL para `dev.ventalibra.com.ar`. Corregir en el
  proveedor de DNS antes de seguir con esta parte.
- [ ] `scripts/nuevo_cliente.py` no captura el plan elegido al crear un
  cliente todavía — todo cliente nuevo arranca en Premium por default.
- [ ] Primer cliente de prueba real (`docker compose` vía
  `scripts/nuevo_cliente.py`, no el contenedor `-dev` manual usado para
  verificar la infraestructura).
- [ ] Frontend React/Vite/Tailwind/shadcn-ui (estándar de la familia).
- [ ] Reportes de ventas, caja y stock.
- Validar con un comercio real antes de sumar promociones avanzadas,
  multi-sucursal o modo offline (ver `wiki/analyses/arquitectura-familia-libra-alcance.md`,
  "Orden de implementación").

## Futuro

- Modo offline (mini PC local) reusando `libraedge`/la integración ya
  construida en LibraCommerce — evaluar una vez validado con un comercio real.
