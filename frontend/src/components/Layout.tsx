// Shim sobre libra-ui/Layout (extraído 2026-07-26, era idéntico en
// Gestiolibra/MedLibra/VentaLibra salvo NAV_ITEMS/branding -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
import {
  ArrowRightLeft,
  Boxes,
  BarChart3, Banknote, BookText, Building2, CalendarCheck, CalendarClock, Clock, Coins, FileSpreadsheet, HandCoins, Landmark,
  LayoutDashboard, Package, PackagePlus, Percent, ReceiptText, ScanBarcode, ScrollText, Settings, ShoppingBag, ShoppingCart, Tags, TrendingUp, Truck,
  Users, Wallet, Warehouse,
} from 'lucide-react'
import { createLayout, type NavSection } from 'libra-ui/Layout'
import { WORDMARK } from '@/branding'
import { sinCapacidad } from '@/lib/permisos'

const NAV_SECCIONES: NavSection<unknown>[] = [
  { items: [{ to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, hideFor: sinCapacidad('dashboard') }] },
  {
    label: 'Mostrador',
    items: [
      // "Venta" pasó a "POS (Caja)" y "Catálogo" a "Productos" (2026-09-17); las rutas no cambian (`/pos`, `/productos`).
      { to: '/pos', label: 'POS (Caja)', icon: ShoppingCart, hideFor: sinCapacidad('ventas.pos') },
      // Para el cajero es también donde se reimprime un comprobante.
      { to: '/ventas', label: 'Ventas', icon: ReceiptText, hideFor: sinCapacidad('ventas.pos') },
      {
        to: '/clientes', label: 'Clientes', icon: Users, hideFor: sinCapacidad('clientes.pantalla'),
        children: [{ to: '/cuentas-corrientes', label: 'Cuentas corrientes', icon: Wallet, hideFor: sinCapacidad('cuenta_corriente') }],
      },
    ],
  },
  {
    label: 'Caja y tesorería',
    items: [
      // Los turnos de caja: cada uno los suyos; el encargado y el admin, los de todos (`turnos.todos`).
      {
        to: '/turnos', label: 'Turnos', icon: Clock, hideFor: sinCapacidad('caja.propia'),
        // El cierre diario es del encargado y el admin (y del staff heredado); el cajero ya no (ADR-049).
        children: [{ to: '/cierre-diario', label: 'Cierre diario', icon: CalendarCheck, hideFor: sinCapacidad('cierre_diario') }],
      },
      { to: '/cajas', label: 'Cajas', icon: Landmark, hideFor: sinCapacidad('caja.admin') },
      // Fase 10 y 11 de la adopción de los motores (ADR-037, ADR-038): sin gate de plan.
      { to: '/tesoreria', label: 'Tesorería', icon: Banknote, hideFor: sinCapacidad('tesoreria') },
      { to: '/egresos', label: 'Egresos', icon: HandCoins, hideFor: sinCapacidad('egresos') },
    ],
  },
  {
    label: 'Catálogo y precios',
    items: [
      {
        to: '/productos', label: 'Productos', icon: Package, hideFor: sinCapacidad('catalogo.pantalla'),
        // Las etiquetas de góndola (ADR-047) se arman con los precios ya cargados.
        children: [{ to: '/etiquetas', label: 'Etiquetas', icon: ScanBarcode, hideFor: sinCapacidad('etiquetas') }],
      },
      {
        to: '/listas-precio', label: 'Listas de precio', icon: Tags, hideFor: sinCapacidad('precios.escribir'),
        children: [
          { to: '/actualizacion-masiva-precios', label: 'Actualización de precios', icon: FileSpreadsheet, hideFor: sinCapacidad('precios.escribir') },
          { to: '/promociones', label: 'Promociones', icon: Percent, hideFor: sinCapacidad('precios.escribir') },
        ],
      },
    ],
  },
  {
    label: 'Inventario',
    items: [
      {
        to: '/stock', label: 'Stock', icon: Boxes, hideFor: sinCapacidad('stock.pantalla'),
        children: [
          // A-3 (ADR-052): qué vence y qué lote sacar. Del encargado y del depósito.
          { to: '/vencimientos', label: 'Vencimientos y lotes', icon: CalendarClock, hideFor: sinCapacidad('vencimientos.ver') },
          // Sin `module`: en Básico sirve entre los depósitos de la misma sucursal; lo que cruza de sucursal lo corta el
          // backend y la pantalla avisa (ADR-048).
          { to: '/transferencias', label: 'Transferencias', icon: ArrowRightLeft, hideFor: sinCapacidad('stock.transferir') },
        ],
      },
      // B-3 (ADR-051): qué pedir y cuánto. Del encargado y, desde ADR-054, del depósito.
      { to: '/reposicion', label: 'Reposición sugerida', icon: PackagePlus, hideFor: sinCapacidad('reposicion.ver') },
      { to: '/sucursales', label: 'Sucursales y depósitos', icon: Warehouse, hideFor: sinCapacidad(['sucursales.admin', 'stock.transferir']) },
    ],
  },
  {
    label: 'Compras',
    items: [
      {
        to: '/compras', label: 'Compras', icon: ShoppingBag, hideFor: sinCapacidad('compras.ver'),
        children: [{ to: '/proveedores', label: 'Proveedores', icon: Truck, hideFor: sinCapacidad('proveedores.pantalla') }],
      },
    ],
  },
  {
    label: 'Reportes',
    items: [
      {
        to: '/reportes', label: 'Reportes', icon: BarChart3, hideFor: sinCapacidad('reportes'),
        children: [
          // ADR-046: margen y rotación por producto y por período.
          { to: '/margen', label: 'Margen y rotación', icon: TrendingUp, hideFor: sinCapacidad('margen') },
          { to: '/caja-medios', label: 'Caja por medio', icon: Coins },
          // Fase 12 (ADR-038): contable-fiscal.
          { to: '/libros-iva', label: 'Libros IVA', icon: BookText, hideFor: sinCapacidad('libros_iva') },
        ],
      },
    ],
  },
  {
    label: 'Administración',
    items: [
      { to: '/usuarios', label: 'Usuarios', icon: Building2, hideFor: sinCapacidad('usuarios.admin') },
      // Junto a Usuarios: se mira para responder "quién hizo esto".
      { to: '/logs', label: 'Logs', icon: ScrollText, hideFor: sinCapacidad('logs') },
      // ARCA, Balanza, Ticket, datos de empresa, correo y backup: secciones de una sola pantalla.
      { to: '/configuracion', label: 'Configuración', icon: Settings, hideFor: sinCapacidad('config') },
    ],
  },
]

export const Layout = createLayout({
  productName: 'VentaLibra',
  productInitial: 'V',
  // La marca (el icono de VentaLibra sobre un cuadrado de su color, libra-ui ADR-033) y el nombre en Montserrat Bold. Las clases del
  // nombre salen de `@/branding`, el mismo archivo que usa el login: es lo que garantiza que las dos pantallas escriban "VentaLibra" igual.
  // `MarcaProducto` ya viene con `h-8 w-8 shrink-0`, que es lo que cabe en la sidebar colapsada (32 px): no hace falta ningun override.
  producto: 'ventalibra',
  // 🔴 El interlineado va PEGADO al tamano (`/[17px]`) y no como `leading-*`
  // aparte: en Tailwind v4 una utilidad de tamano emite tambien `line-height`,
  // asi que el `leading-none` que libra-ui pone por defecto perderia contra
  // este `text-[15px]` y el nombre se quedaria con 22,5 px de caja.
  // 17 = 32 (el alto de la marca) menos los 15 de la linea de la empresa.
  wordmarkClassName: `${WORDMARK} text-[15px]/[17px]`,
  // 🔴 El menú lo decide `hideFor` con las CAPACIDADES del usuario (`lib/permisos.ts`, ADR-049), no `adminOnly`: con
  // cinco roles «admin o no» no alcanza. Sólo esconde: el que corta es el backend. El visitante de la demo (`demo_readonly`)
  // ve todos los menús, como siempre.
  //
  // Dos niveles (ADR-054, pedido del humano 2026-10-01): la SECCIÓN (Mostrador, Caja, Catálogo, Inventario, Compras,
  // Reportes, Administración) y, dentro, los ítems con sus subpantallas anidadas. La misma forma que Contalibra y Restolibra.
  // Una sección sin ítems visibles no se dibuja, así que cada rol ve sólo lo suyo; un hijo cuelga de un padre que su rol
  // también ve (verificado en `roles-menu-y-rutas.test.tsx`).
  navSections: NAV_SECCIONES,
  // El nombre del negocio, debajo de «VentaLibra» (viene de Configuración > Datos de empresa, vía `/auth/me`).
  getUserSubtitle: (u) => (u as { empresa_nombre?: string }).empresa_nombre,
})
