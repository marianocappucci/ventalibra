// Shim sobre libra-ui/Login (extraído 2026-07-26, era idéntico en
// Gestiolibra/MedLibra/VentaLibra salvo branding/redirectTo -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
import { createLogin } from 'libra-ui/Login'

export const Login = createLogin({
  productName: 'VentaLibra',
  productInitial: 'V',
  redirectTo: '/pos',
})
