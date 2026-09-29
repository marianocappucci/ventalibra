// Shim sobre libra-ui/Layout (extraído 2026-07-26, era idéntico en
// Gestiolibra/MedLibra/VentaLibra salvo NAV_ITEMS/branding -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
import {
  ArrowRightLeft,
  Boxes,
  BarChart3, Banknote, BookText, Building2, CalendarCheck, Clock, Coins, FileSpreadsheet, HandCoins, Landmark,
  LayoutDashboard, Package, Percent, ReceiptText, ScanBarcode, ScrollText, Settings, ShoppingBag, ShoppingCart, Tags, TrendingUp, Truck,
  Users, Wallet, Warehouse,
} from 'lucide-react'
import { createLayout } from 'libra-ui/Layout'
import { LOGO, WORDMARK } from '@/branding'
import { sinCapacidad } from '@/lib/permisos'

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
  // 🔴 El menú lo decide `hideFor` con las CAPACIDADES del usuario (`lib/permisos.ts`, ADR-049), no `adminOnly`: con
  // cinco roles «admin o no» no alcanza. Sólo esconde: el que corta es el backend. El visitante de la demo (`demo_readonly`)
  // ve todos los menús, como siempre.
  navItems: [
    // "Venta" pasó a "POS (Caja)" y "Catálogo" a "Productos" (2026-09-17,
    // pedido del humano); las rutas no cambian (`/pos`, `/productos` —
    // `/catalogo` redirige, ver `rutas-viejas.ts`).
    { to: '/pos', label: 'POS (Caja)', icon: ShoppingCart, hideFor: sinCapacidad('ventas.pos') },
    { to: '/ventas', label: 'Ventas', icon: ReceiptText, hideFor: sinCapacidad('ventas.pos') },
    { to: '/productos', label: 'Productos', icon: Package, hideFor: sinCapacidad('catalogo.ver') },
    { to: '/compras', label: 'Compras', icon: ShoppingBag, hideFor: sinCapacidad('compras.ver') },
    { to: '/proveedores', label: 'Proveedores', icon: Truck, hideFor: sinCapacidad('compras.ver') },
    // Fase 11 de la adopción de los motores (ADR-038): complementa a Compras, la contabilidad del pago.
    { to: '/egresos', label: 'Egresos', icon: HandCoins, hideFor: sinCapacidad('egresos') },
    { to: '/clientes', label: 'Clientes', icon: Users, hideFor: sinCapacidad('clientes.ver') },
    { to: '/cuentas-corrientes', label: 'Cuentas corrientes', icon: Wallet, hideFor: sinCapacidad('cuenta_corriente') },
    { to: '/sucursales', label: 'Sucursales', icon: Warehouse, hideFor: sinCapacidad(['sucursales.admin', 'stock.transferir']) },
    { to: '/listas-precio', label: 'Listas de precio', icon: Tags, hideFor: sinCapacidad('precios.escribir') },
    // Roadmap de producto (2026-09-28): no es una adopción de motores, es la primera mejora del
    // roadmap propio de VentaLibra (ver wiki/analyses/ventalibra-gaps-despensa.md).
    { to: '/actualizacion-masiva-precios', label: 'Actualización de precios', icon: FileSpreadsheet, hideFor: sinCapacidad('precios.escribir') },
    { to: '/promociones', label: 'Promociones', icon: Percent, hideFor: sinCapacidad('precios.escribir') },
    // Roadmap de producto (2026-09-29, ADR-047): las etiquetas de góndola se arman con los precios ya cargados.
    { to: '/etiquetas', label: 'Etiquetas', icon: ScanBarcode, hideFor: sinCapacidad('etiquetas') },
    { to: '/stock', label: 'Stock', icon: Boxes, hideFor: sinCapacidad('stock.ver') },
    // Sin `module`: en Básico sirve entre los depósitos de la misma sucursal; lo que cruza de sucursal lo corta el
    // backend y la pantalla avisa (ADR-048).
    { to: '/transferencias', label: 'Transferencias', icon: ArrowRightLeft, hideFor: sinCapacidad('stock.transferir') },
    { to: '/cajas', label: 'Cajas', icon: Landmark, hideFor: sinCapacidad('caja.admin') },
    // Fase 10 de la adopción de los motores (ADR-037): cuentas bancarias y transferencias, sin gate de plan.
    { to: '/tesoreria', label: 'Tesorería', icon: Banknote, hideFor: sinCapacidad('tesoreria') },
    // Los turnos de caja: cada uno los suyos; el encargado y el admin, los de todos (`turnos.todos`).
    { to: '/turnos', label: 'Turnos', icon: Clock, hideFor: sinCapacidad('caja.propia') },
    // El cierre diario es del encargado y el admin (y del staff heredado); el cajero ya no (ADR-049).
    { to: '/cierre-diario', label: 'Cierre diario', icon: CalendarCheck, hideFor: sinCapacidad('cierre_diario') },
    // Fase 13 de la adopción de los motores (ADR-039). Libre en todos los planes desde ADR-048: el plan se
    // distingue por facturación ARCA y multisucursal, no por el tablero.
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, hideFor: sinCapacidad('dashboard') },
    { to: '/reportes', label: 'Reportes', icon: BarChart3, hideFor: sinCapacidad('reportes') },
    // Roadmap de producto, tanda 1 (2026-09-29, ADR-046): margen y rotación por producto y por período.
    { to: '/margen', label: 'Margen y rotación', icon: TrendingUp, hideFor: sinCapacidad('margen') },
    // Fase 12 de la adopción de los motores (ADR-038): ventas ya funciona, compras se completa con Egresos.
    { to: '/libros-iva', label: 'Libros IVA', icon: BookText, hideFor: sinCapacidad('libros_iva') },
    { to: '/caja-medios', label: 'Caja por medio', icon: Coins, hideFor: sinCapacidad('reportes') },
    { to: '/usuarios', label: 'Usuarios', icon: Building2, hideFor: sinCapacidad('usuarios.admin') },
    // Junto a Usuarios: se mira para responder "quién hizo esto".
    { to: '/logs', label: 'Logs', icon: ScrollText, hideFor: sinCapacidad('logs') },
    // Las tres entradas de configuración que había acá —ARCA, Balanza y
    // Ticket— pasaron a ser secciones de una sola pantalla, junto con datos de
    // empresa, correo y backup, que antes no tenían dónde vivir.
    { to: '/configuracion', label: 'Configuración', icon: Settings, hideFor: sinCapacidad('config') },
  ],
})
