// Shim sobre libra-ui/Layout (extraído 2026-07-26, era idéntico en
// Gestiolibra/MedLibra/VentaLibra salvo NAV_ITEMS/branding -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
import {
  BarChart3, Building2, Package, ReceiptText, ScrollText, Settings,
  ShoppingBag, ShoppingCart, Truck, Users, Wallet, Warehouse,
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
    { to: '/pos', label: 'Venta', icon: ShoppingCart },
    { to: '/ventas', label: 'Ventas', icon: ReceiptText },
    { to: '/catalogo', label: 'Catálogo', icon: Package },
    { to: '/compras', label: 'Compras', icon: ShoppingBag },
    { to: '/proveedores', label: 'Proveedores', icon: Truck },
    { to: '/clientes', label: 'Clientes', icon: Users },
    { to: '/cuentas-corrientes', label: 'Cuentas corrientes', icon: Wallet },
    { to: '/sucursales', label: 'Sucursales', icon: Warehouse },
    { to: '/reportes', label: 'Reportes', icon: BarChart3, adminOnly: true },
    { to: '/usuarios', label: 'Usuarios', icon: Building2, adminOnly: true },
    // Junto a Usuarios: se mira para responder "quién hizo esto".
    { to: '/logs', label: 'Logs', icon: ScrollText, adminOnly: true },
    // Las tres entradas de configuración que había acá —ARCA, Balanza y
    // Ticket— pasaron a ser secciones de una sola pantalla, junto con datos de
    // empresa, correo y backup, que antes no tenían dónde vivir.
    { to: '/configuracion', label: 'Configuración', icon: Settings, adminOnly: true },
  ],
})
