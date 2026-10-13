import type { Credenciales } from 'libra-ui/e2e'

// Los usuarios de la instancia de prueba: el admin de siempre y uno por rol, que crea `scripts/e2e_usuarios.py` por la API
// antes de correr. Las contraseñas son las del CI (`.github/workflows/e2e.yml`), no un secreto.
export type Rol = 'admin' | 'encargado' | 'vendedor' | 'cajero' | 'deposito'

const CLAVE = process.env.E2E_CLAVE ?? 'e2e-Clave-1234'

export const ROLES: Record<Rol, Credenciales> = {
  admin: { usuario: process.env.E2E_ADMIN_USUARIO ?? 'admin', clave: process.env.E2E_ADMIN_CLAVE ?? '' },
  encargado: { usuario: 'e2e_encargado', clave: CLAVE },
  vendedor: { usuario: 'e2e_vendedor', clave: CLAVE },
  cajero: { usuario: 'e2e_cajero', clave: CLAVE },
  deposito: { usuario: 'e2e_deposito', clave: CLAVE },
}
