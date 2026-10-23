'use client'

import { useLocale, useTranslations } from 'next-intl'
import { LANGUAGES, languageOf } from '@/i18n/config'
import { useSetLocale } from '@/i18n/setLocale'
import { SettingsSection } from './SettingsSection'

/** The language of the interface, the answers and the reports. Saved in a cookie for a year. */
export function LanguageSection() {
  const t = useTranslations('impostazioni.language')
  const locale = useLocale()
  const setLocale = useSetLocale()
  const current = languageOf(locale)

  return (
    <SettingsSection id="lingua" title={t('title')} description={t('description')}>
      <fieldset>
        <legend className="sr-only">{t('legend')}</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {LANGUAGES.map((language) => {
            const id = `lingua-${language}`
            const selected = current === language
            return (
              <label
                key={language}
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
                  value={language}
                  checked={selected}
                  onChange={() => setLocale(language)}
                  className="mt-1 h-4 w-4 border-rule-2 text-union focus:ring-union/30"
                />
                <span>
                  <span className="block text-body font-medium text-ink" lang={language}>
                    {t(`options.${language}.label`)}
                  </span>
                  <span className="block text-caption text-ink-3">{t(`options.${language}.hint`)}</span>
                </span>
              </label>
            )
          })}
        </div>
      </fieldset>
      <p className="mt-3 text-caption text-ink-3">{t('note')}</p>
    </SettingsSection>
  )
}
