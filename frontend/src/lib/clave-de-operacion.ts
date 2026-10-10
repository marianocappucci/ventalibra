// Un identificador único por intento de una operación que el motor puede reconocer como reintento (`clave_operacion`; hoy,
// `POST /api/ventas/{vid}/devolver`, ADR-041 de libracommerce).
//
// Es la misma función que `libra-ui/src/comercio/clave-de-operacion.ts` (la usan Vencimientos y Reposición del kit), copiada acá
// porque el kit todavía no la exporta (`libra-ui/package.json` no tiene `./comercio/clave-de-operacion`). Cuando la exporte, esto se
// reemplaza por el import.
//
// `randomUUID` sólo existe en contextos seguros (https o localhost): un producto servido por http en la red local cae al generador
// de `getRandomValues`, que sí está siempre.
export function nuevaClaveDeOperacion(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const b = crypto.getRandomValues(new Uint8Array(16))
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}
