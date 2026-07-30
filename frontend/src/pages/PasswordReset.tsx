// Shim sobre libra-ui/PasswordReset (mismo patrón que Login/Usuarios).
// Las dos pantallas son públicas: van fuera de ProtectedRoute en App.tsx,
// porque quien las usa justamente no puede entrar.
import { createForgotPassword, createResetPassword } from 'libra-ui/PasswordReset'

const branding = { productName: 'VentaLibra', productInitial: 'V' }

export const ForgotPassword = createForgotPassword(branding)
export const ResetPassword = createResetPassword(branding)
