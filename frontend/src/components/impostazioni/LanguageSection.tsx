'use client'

import { useLocale } from '@/hooks/useLocale'
import { SettingsSection } from './SettingsSection'

const OPTIONS: Array<{ value: 'it' | 'en'; label: string; hint: string }> = [
  { value: 'it', label: 'Italiano', hint: 'Risposte e report in italiano.' },
  { value: 'en', label: 'English', hint: 'Risposte e report in inglese.' },
]

/** The preferred language for generated answers. The interface stays in Italian. */
export function LanguageSection() {
  const { locale, setLocale } = useLocale()
  const current = locale === 'en' ? 'en' : 'it'

  return (
    <SettingsSection
      id="lingua"
      title="Lingua"
      description="La lingua preferita per le risposte e i report. L’interfaccia resta in italiano."
    >
      <fieldset>
        <legend className="sr-only">Lingua delle risposte</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {OPTIONS.map((opt) => {
            const id = `lingua-${opt.value}`
            const selected = current === opt.value
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
                  name="lingua"
                  value={opt.value}
                  checked={selected}
                  onChange={() => setLocale(opt.value)}
                  className="mt-1 h-4 w-4 border-rule-2 text-union focus:ring-union/30"
                />
                <span>
                  <span className="block text-body font-medium text-ink">{opt.label}</span>
                  <span className="block text-caption text-ink-3">{opt.hint}</span>
                </span>
              </label>
            )
          })}
        </div>
      </fieldset>
      <p className="mt-3 text-caption text-ink-3">La preferenza è salvata su questo browser.</p>
    </SettingsSection>
  )
}
