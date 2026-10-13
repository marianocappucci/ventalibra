// Las pestañas del kit (`libra-ui/ui/tabs`, ADR-058 §6 del kit; ADR-083 de este repo): el mismo primitivo de shadcn/ui sobre `radix-ui`
// que VentaLibra traía copiado (ocho productos tenían la misma copia byte a byte), con `activationMode="manual"` por defecto
// (2026-10-09: con el automático de Radix la pestaña con foco se reactiva sola y el «atrás» del navegador no vuelve en las pestañas
// atadas a la URL). Se reexporta acá para que el código del producto que importa `@/components/ui/tabs` siga igual.
export * from 'libra-ui/ui/tabs'
