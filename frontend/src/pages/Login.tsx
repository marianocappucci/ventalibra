// Shim sobre libra-ui/Login (extraído 2026-07-26, era idéntico en
// Gestiolibra/MedLibra/VentaLibra salvo branding/redirectTo -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
import { createLogin } from 'libra-ui/Login'
import { LOGO, WORDMARK } from '@/branding'

export const Login = createLogin({
  productName: 'VentaLibra',
  productInitial: 'V',
  // El logo y el nombre en Montserrat Bold (libra-ui v0.23.0). `productInitial`
  // sigue arriba porque es el fallback del motor: si el asset no resuelve, la
  // pantalla muestra la inicial en vez de un hueco.
  logo: { src: LOGO, className: 'h-[72px] w-[72px]' },
  wordmarkClassName: `${WORDMARK} text-[22px]`,
  redirectTo: '/pos',
  // Enlace "¿Olvidaste tu contraseña?" -- va de la mano con
  // incluir_password_reset=True en app/routers/auth.py.
  forgotPasswordPath: '/forgot-password',
  // Boton "Entrar a la demo" -- va de la mano con incluir_demo=True en
  // app/routers/auth.py. Declararlo aca NO alcanza para que se muestre:
  // libra-ui consulta GET /auth/demo al montar y solo lo pinta si la
  // instancia contesta que es una demo.
  demoPath: '/auth/demo',
})
