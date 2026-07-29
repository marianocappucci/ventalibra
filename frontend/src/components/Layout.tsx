// Shim sobre libra-ui/Layout (extraído 2026-07-26, era idéntico en
// Gestiolibra/MedLibra/VentaLibra salvo NAV_ITEMS/branding -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
import {
  BarChart3, Building2, Package, Receipt, Scale, ShoppingBag, ShoppingCart, Truck, Users,
  Warehouse,
} from 'lucide-react'
import { createLayout } from 'libra-ui/Layout'

export const Layout = createLayout({
  productName: 'VentaLibra',
  productInitial: 'V',
  navItems: [
    { to: '/pos', label: 'Venta', icon: ShoppingCart },
    { to: '/catalogo', label: 'Catálogo', icon: Package },
    { to: '/compras', label: 'Compras', icon: ShoppingBag },
    { to: '/proveedores', label: 'Proveedores', icon: Truck },
    { to: '/clientes', label: 'Clientes', icon: Users },
    { to: '/sucursales', label: 'Sucursales', icon: Warehouse },
    { to: '/reportes', label: 'Reportes', icon: BarChart3, adminOnly: true },
    { to: '/usuarios', label: 'Usuarios', icon: Building2, adminOnly: true },
    { to: '/config-arca', label: 'Config. ARCA', icon: Receipt, adminOnly: true },
    { to: '/config-balanza', label: 'Balanza', icon: Scale, adminOnly: true },
  ],
})
