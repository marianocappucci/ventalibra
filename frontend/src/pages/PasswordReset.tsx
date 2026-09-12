// Shim sobre libra-ui/PasswordReset (mismo patrón que Login/Usuarios).
// Las dos pantallas son públicas: van fuera de ProtectedRoute en App.tsx,
// porque quien las usa justamente no puede entrar.
import { createForgotPassword, createResetPassword } from 'libra-ui/PasswordReset'

const branding = { productName: 'VentaLibra', productInitial: 'V' }

// El captcha va tambien en «olvidé mi contraseña»: con captcha=True libraauth
// lo exige ahi (sin el, el endpoint manda correos a pedido de cualquiera). El
// reset-password no lo lleva: ya viene con el token del mail.
export const ForgotPassword = createForgotPassword({ ...branding, captchaPath: '/auth/captcha' })
export const ResetPassword = createResetPassword(branding)
