// Shim sobre libra-ui/utils (extraído 2026-07-26, era byte-idéntico en
// Gestiolibra/MedLibra/VentaLibra -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
export { cn } from 'libra-ui/utils'

// Redondeo a entero para mostrar cantidades de stock (lo usan las pantallas de stock y depósitos del kit,
// `libra-ui/comercio`, igual que en Contalibra). Solo para visualización; los valores reales siguen siendo float en la API.
export function formatEntero(value: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) return String(value)
  return String(Math.round(value))
}
