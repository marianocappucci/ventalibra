import { prepararSesiones } from 'libra-ui/e2e'
import { ROLES } from './roles'

// Un login por rol, una sola vez por corrida: deja `.auth/<rol>.json` y los specs `*.e2e.ts` arrancan ya adentro.
prepararSesiones(ROLES)
