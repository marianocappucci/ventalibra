// El diálogo «¿Vender igual?» del POS (ADR-053): se abre ANTES de cobrar cuando el plan de salida dice que el carrito lleva mercadería de
// un lote vencido o por vencer. No bloquea: «Vender igual» sigue con la venta y «Volver» vuelve al cobro sin registrar nada.
//
// 🔴 `onDecidir` se llama UNA sola vez por diálogo: Radix cierra el diálogo al apretar un botón (y llama a `onOpenChange`) después del
// `onClick`, y un doble clic en «Vender igual» no puede registrar dos ventas. El guardia es un `useRef` (vale YA, sin esperar al
// próximo render), como el de `Cobro`.
import { useRef } from 'react'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { describirAviso, tituloDeAvisos, type AvisoDeVencimiento } from '../lib/avisos-de-vencimiento'

export function DialogoAvisosDeVencimiento({ avisos, onDecidir }: {
  avisos: AvisoDeVencimiento[]
  onDecidir: (seguir: boolean) => void
}) {
  const decididoRef = useRef(false)
  function decidir(seguir: boolean) {
    if (decididoRef.current) return
    decididoRef.current = true
    onDecidir(seguir)
  }
  return (
    <AlertDialog open onOpenChange={(abierto) => { if (!abierto) decidir(false) }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{tituloDeAvisos(avisos)}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div>
              <ul className="list-disc space-y-1 pl-5 text-left">
                {avisos.map((a, i) => <li key={i}>{describirAviso(a)}</li>)}
              </ul>
              <p className="mt-3 font-medium text-foreground">¿Vender igual?</p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Volver</AlertDialogCancel>
          <AlertDialogAction onClick={() => decidir(true)}>Vender igual</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
