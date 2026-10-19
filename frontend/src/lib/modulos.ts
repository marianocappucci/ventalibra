// Qué módulos del plan tiene prendidos la instancia, tal como los manda `/auth/me` (`modulos`: la lista de los
// habilitados; ver `app/routers/auth.py`, ADR-048). Con el plan único (ADR-072) vienen todos prendidos.
//
// 🔴 **Sólo decide qué se muestra: el que corta es el backend.** Cada endpoint gateado contesta 403 con o sin este
// aviso (`require_module`, y para la segunda sucursal y la transferencia entre sucursales
// `app/depositos_ganchos.py`). Por eso la degradación va hacia mostrar: si el campo no viene (un backend viejo, o
// uno al que le falló la consulta), todavía no hay usuario o la pantalla se monta sin `ModulosContext.Provider`
// (así se prueban sueltas), se ofrece todo y la primera acción que no corresponda recibe el 403 con su mensaje.
// Ocultarle a un cliente lo que tiene contratado por un fallo transitorio es peor que un botón de más.
import { createContext, useContext } from 'react'

/** Más de una sucursal y la transferencia de mercadería entre sucursales (incluido en el plan único). */
export const MULTISUCURSAL = 'multisucursal'
/** Facturación electrónica ARCA (incluida en el plan único). */
export const FACTURACION = 'facturacion'

/** La lista de módulos habilitados del usuario, o `undefined` si el backend no la mandó. */
export function modulosDe(user: unknown): string[] | undefined {
  const modulos = (user as { modulos?: unknown } | null)?.modulos
  return Array.isArray(modulos) ? (modulos as string[]) : undefined
}

export function tieneModulo(modulos: string[] | undefined, modulo: string): boolean {
  return modulos === undefined ? true : modulos.includes(modulo)
}

/** Lo provee `ProtectedRoute` (App.tsx) con los módulos del usuario en sesión. */
export const ModulosContext = createContext<string[] | undefined>(undefined)

export function useTieneModulo(modulo: string): boolean {
  return tieneModulo(useContext(ModulosContext), modulo)
}
