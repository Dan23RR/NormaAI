'use client'

import { useRouter } from 'next/navigation'
import { LogOut } from 'lucide-react'
import { Button } from '@/components/ui'
import { useAuth } from '@/hooks/useAuth'
import { SettingsSection } from './SettingsSection'

/** Shown only in the demo: what it is, what it is not, how to leave it. */
export function DemoSection() {
  const { logout } = useAuth()
  const router = useRouter()

  const leave = () => {
    logout()
    router.replace('/login')
  }

  return (
    <SettingsSection id="demo" title="Demo" description="Stai usando la demo con dati di esempio.">
      <div className="rounded-lg border border-mark-deep/40 bg-mark/20 p-5">
        <p className="max-w-prose text-body text-ink">
          Le risposte, i clienti e le analisi non vengono dal corpus normativo né dal tuo account: sono esempi fissi,
          generati senza chiamare il server. Clienti e report creati nella demo restano in questa sessione del browser.
        </p>
        <Button className="mt-4" variant="secondary" onClick={leave} iconLeft={<LogOut className="h-4 w-4" aria-hidden="true" />}>
          Esci dalla demo
        </Button>
      </div>
    </SettingsSection>
  )
}
