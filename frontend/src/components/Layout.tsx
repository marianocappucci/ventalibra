// Shim sobre libra-ui/Layout (extraído 2026-07-26, era idéntico en
// Gestiolibra/MedLibra/VentaLibra salvo NAV_ITEMS/branding -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
import {
  ArrowRightLeft,
  Boxes,
  BarChart3, Banknote, BookText, Building2, CalendarCheck, Clock, Coins, FileSpreadsheet, HandCoins, Landmark,
  LayoutDashboard, Package, Percent, ReceiptText, ScrollText, Settings, ShoppingBag, ShoppingCart, Tags, TrendingUp, Truck, Users, Wallet,
  Warehouse,
} from 'lucide-react'
import { createLayout } from 'libra-ui/Layout'
import { LOGO, WORDMARK } from '@/branding'

export const Layout = createLayout({
  productName: 'VentaLibra',
  productInitial: 'V',
  // El logo y el nombre en Montserrat Bold. Las clases salen de `@/branding`,
  // el mismo archivo que usa el login: es lo que garantiza que las dos
  // pantallas escriban "VentaLibra" igual.
  //
  // El override de colapsado NO es decorativo: con la sidebar en modo icono el
  // ancho util son 32 px y sin bajarlo el logo de 36 se sale de la barra.
  logo: {
    src: LOGO,
    className: 'h-9 w-9 group-data-[collapsible=icon]:h-8 group-data-[collapsible=icon]:w-8',
  },
  // 🔴 El interlineado va PEGADO al tamano (`/[21px]`) y no como `leading-*`
  // aparte: en Tailwind v4 una utilidad de tamano emite tambien `line-height`,
  // asi que el `leading-none` que libra-ui pone por defecto perderia contra
  // este `text-[15px]` y el nombre se quedaria con 22,5 px de caja.
  // 21 = 36 (el alto del logo) menos los 15 de la linea de la empresa.
  wordmarkClassName: `${WORDMARK} text-[15px]/[21px]`,
  navItems: [
    // "Venta" pasó a "POS (Caja)" y "Catálogo" a "Productos" (2026-09-17,
    // pedido del humano); las rutas no cambian (`/pos`, `/productos` —
    // `/catalogo` redirige, ver `rutas-viejas.ts`).
    { to: '/pos', label: 'POS (Caja)', icon: ShoppingCart },
    { to: '/ventas', label: 'Ventas', icon: ReceiptText },
    { to: '/productos', label: 'Productos', icon: Package },
    { to: '/compras', label: 'Compras', icon: ShoppingBag },
    { to: '/proveedores', label: 'Proveedores', icon: Truck },
    // Fase 11 de la adopción de los motores (ADR-038): complementa a Compras, la contabilidad del pago.
    { to: '/egresos', label: 'Egresos', icon: HandCoins },
    { to: '/clientes', label: 'Clientes', icon: Users },
    { to: '/cuentas-corrientes', label: 'Cuentas corrientes', icon: Wallet },
    { to: '/sucursales', label: 'Sucursales', icon: Warehouse },
    { to: '/listas-precio', label: 'Listas de precio', icon: Tags, adminOnly: true },
    // Roadmap de producto (2026-09-28): no es una adopción de motores, es la primera mejora del
    // roadmap propio de VentaLibra (ver wiki/analyses/ventalibra-gaps-despensa.md).
    { to: '/actualizacion-masiva-precios', label: 'Actualización de precios', icon: FileSpreadsheet, adminOnly: true },
    { to: '/promociones', label: 'Promociones', icon: Percent, adminOnly: true },
    { to: '/stock', label: 'Stock', icon: Boxes },
    { to: '/transferencias', label: 'Transferencias', icon: ArrowRightLeft },
    { to: '/cajas', label: 'Cajas', icon: Landmark, adminOnly: true },
    // Fase 10 de la adopción de los motores (ADR-037): cuentas bancarias y transferencias, sin gate de plan.
    { to: '/tesoreria', label: 'Tesorería', icon: Banknote, adminOnly: true },
    // Los turnos de caja: cada cajero los suyos, el admin todos.
    { to: '/turnos', label: 'Turnos', icon: Clock },
    // Admin y cajero: el cierre diario lo puede hacer cualquiera de los dos.
    { to: '/cierre-diario', label: 'Cierre diario', icon: CalendarCheck },
    // Fase 13 de la adopción de los motores (ADR-039): gateado a "premium" (plans.py), a diferencia de
    // Tesorería/Egresos/Libros IVA. Sin nav-hiding por módulo: un admin de otro plan ve el 403 del motor.
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, adminOnly: true },
    { to: '/reportes', label: 'Reportes', icon: BarChart3, adminOnly: true },
    // Roadmap de producto, tanda 1 (2026-09-29, ADR-046): margen y rotación por producto y por período.
    { to: '/margen', label: 'Margen y rotación', icon: TrendingUp, adminOnly: true },
    // Fase 12 de la adopción de los motores (ADR-038): ventas ya funciona, compras se completa con Egresos.
    { to: '/libros-iva', label: 'Libros IVA', icon: BookText, adminOnly: true },
    { to: '/caja-medios', label: 'Caja por medio', icon: Coins, adminOnly: true },
    { to: '/usuarios', label: 'Usuarios', icon: Building2, adminOnly: true },
    // Junto a Usuarios: se mira para responder "quién hizo esto".
    { to: '/logs', label: 'Logs', icon: ScrollText, adminOnly: true },
    // Las tres entradas de configuración que había acá —ARCA, Balanza y
    // Ticket— pasaron a ser secciones de una sola pantalla, junto con datos de
    // empresa, correo y backup, que antes no tenían dónde vivir.
    { to: '/configuracion', label: 'Configuración', icon: Settings, adminOnly: true },
  ],
})
