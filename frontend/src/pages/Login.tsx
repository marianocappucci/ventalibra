// Shim sobre libra-ui/Login (extraído 2026-07-26, era idéntico en
// Gestiolibra/MedLibra/VentaLibra salvo branding/redirectTo -- ver
// wiki/analyses/auditoria-duplicacion-familia-libra.md).
import { createLogin } from 'libra-ui/Login'
import { WORDMARK } from '@/branding'

export const Login = createLogin({
  productName: 'VentaLibra',
  productInitial: 'V',
  // La marca (icono sobre un cuadrado del color del producto, libra-ui ADR-033) y el nombre en Montserrat Bold. `productInitial` sigue arriba
  // porque es obligatorio en la config del motor, aunque con `producto` ya no se dibuja.
  producto: 'ventalibra',
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
  // Captcha «No soy un robot» (ALTCHA, libra-ui v0.69.0) -- va de la mano con
  // captcha=True en app/routers/auth.py. Igual que `demoPath`, libra-ui sondea
  // la ruta al montar y solo dibuja el recuadro si contesta un desafio; con el
  // recuadro puesto, «Ingresar» espera a que se tilde.
  captchaPath: '/auth/captcha',
})
