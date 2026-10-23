'use client'

import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'
import { SettingsSection } from './SettingsSection'

/** Same key and class as AppShell and the pre-paint script in layout.tsx. */
const THEME_KEY = 'normaai.theme'

type Theme = 'light' | 'dark'

const OPTIONS: Array<{ value: Theme; label: string; hint: string; icon: typeof Sun }> = [
  { value: 'light', label: 'Chiaro', hint: 'Fondo bianco su scrivania neutra.', icon: Sun },
  { value: 'dark', label: 'Scuro', hint: 'Per lavorare con poca luce.', icon: Moon },
]

export function ThemeSection() {
  const [theme, setTheme] = useState<Theme>('light')

  useEffect(() => {
    setTheme(document.documentElement.classList.contains('dark') ? 'dark' : 'light')
  }, [])

  const apply = (next: Theme) => {
    document.documentElement.classList.toggle('dark', next === 'dark')
    try {
      localStorage.setItem(THEME_KEY, next)
    } catch {
      /* the choice holds for this page only */
    }
    setTheme(next)
  }

  return (
    <SettingsSection id="tema" title="Tema" description="Chiaro di default, scuro se preferisci.">
      <fieldset>
        <legend className="sr-only">Tema dell’interfaccia</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {OPTIONS.map((opt) => {
            const id = `tema-${opt.value}`
            const selected = theme === opt.value
            return (
              <label
                key={opt.value}
                htmlFor={id}
                className={
                  'flex cursor-pointer items-start gap-3 rounded-lg border px-4 py-3 transition-colors ' +
                  (selected ? 'border-union bg-union/5' : 'border-rule bg-surface hover:border-rule-2')
                }
              >
                <input
                  id={id}
                  type="radio"
                  name="tema"
                  value={opt.value}
                  checked={selected}
                  onChange={() => apply(opt.value)}
                  className="mt-1 h-4 w-4 border-rule-2 text-union focus:ring-union/30"
                />
                <opt.icon className="mt-0.5 h-4 w-4 shrink-0 text-ink-2" aria-hidden="true" />
                <span>
                  <span className="block text-body font-medium text-ink">{opt.label}</span>
                  <span className="block text-caption text-ink-3">{opt.hint}</span>
                </span>
              </label>
            )
          })}
        </div>
      </fieldset>
      <p className="mt-3 text-caption text-ink-3">La scelta è salvata su questo browser.</p>
    </SettingsSection>
  )
}
