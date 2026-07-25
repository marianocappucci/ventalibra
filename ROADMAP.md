# Roadmap — TiendaLibra

Dirección estratégica del producto. No usar para tareas pequeñas del sprint
(ver `TASKS.md`).

## Objetivo actual

- [x] Fase 1: probar de punta a punta que TiendaLibra puede componer
  LibraCore (auth) + LibraCommerce (catálogo/inventario/ventas) con un
  flujo de POS real, antes de construir el resto del alcance.
- [x] Fase 2: compras (orden/recepción con orquestación de stock).

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

### Fase 3 — Caja y facturación ARCA

- Segunda base SQLite dedicada a `libracore.db` (mismo patrón que
  `medlibra/app/services/billing.py`): `init_core_schema`, `caja`,
  `arca_facturacion`.
- Decisión pendiente en esa fase: si conviene reusar `libracore.db.usuarios`
  para esa base en vez de mantener una tabla de usuarios propia (para
  entonces ya existiría de todos modos).

### Fase 4 — Extensiones de catálogo (requieren tocar LibraCommerce primero)

- Códigos de barra (`item_codes`), variantes de talle/color
  (`item_variants`), listas de precio (`price_lists`/`item_prices`),
  productos pesables. Ninguno de estos existe todavía en LibraCommerce —
  son extensiones al motor compartido, no al vertical, según el propio
  análisis de arquitectura de la familia. Se decide de forma explícita
  cuando se llegue a esta fase, no de pasada.

### Fase 5 — Onboarding, planes, frontend, reportes

- Onboarding multi-cliente con enforcement de planes (mismo patrón que
  GestioLibra/MedLibra).
- Frontend React/Vite/Tailwind/shadcn-ui (estándar de la familia).
- Reportes de ventas, caja y stock.
- Validar con un comercio real antes de sumar promociones avanzadas,
  multi-sucursal o modo offline (ver `wiki/analyses/arquitectura-familia-libra-alcance.md`,
  "Orden de implementación").

## Futuro

- Modo offline (mini PC local) reusando `libraedge`/la integración ya
  construida en LibraCommerce — evaluar una vez validado con un comercio real.
