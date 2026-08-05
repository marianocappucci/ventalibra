// Shim sobre libra-ui/Layout (extraído 2026-07-26, era idéntico en
// Gestiolibra/MedLibra/VentaLibra salvo NAV_ITEMS/branding -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
import {
  BarChart3, Building2, Package, ReceiptText, ScrollText, Settings,
  ShoppingBag, ShoppingCart, Truck, Users, Wallet, Warehouse,
} from 'lucide-react'
import { createLayout } from 'libra-ui/Layout'

export const Layout = createLayout({
  productName: 'VentaLibra',
  productInitial: 'V',
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
