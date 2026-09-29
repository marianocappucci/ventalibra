// El aviso de lo que el plan Básico no incluye. Va arriba de la pantalla, o en lugar del contenido cuando no hay nada
// que ofrecer. `role="note"` y no `alert`: no es un error, es información que el usuario ya sabe buscar.
import { Lock } from 'lucide-react'
import type { ReactNode } from 'react'

export function AvisoPremium({ titulo, children }: { titulo: string; children?: ReactNode }) {
  return (
    <div role="note" className="flex items-start gap-3 rounded-lg border bg-muted/50 p-4 text-sm">
      <Lock className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
      <div className="grid gap-1">
        <p className="font-medium">{titulo}: disponible en Premium</p>
        {children && <p className="text-muted-foreground">{children}</p>}
      </div>
    </div>
  )
}
