'use client'

import { createContext, useContext, useState, useCallback, ReactNode } from 'react'

type Locale = 'it' | 'en' | 'de'

interface LocaleContextType {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: (key: string) => string
}

const LOCALE_KEY = 'normaai_locale'

const translations: Record<Locale, Record<string, string>> = {
  it: {
    'nav.overview': 'Overview',
    'nav.qa': 'Q&A Normativo',
    'nav.gap_analysis': 'Gap Analysis',
    'nav.monitor': 'Monitor Modifiche',
    'nav.cross_framework': 'Cross-Framework',
    'nav.alerts': 'Avvisi',
    'nav.reg_feed': 'Feed Normativo',
    'nav.documents': 'Documenti',
    'nav.reports': 'Report',
    'nav.clients': 'Clienti',
    'nav.audit_trail': 'Audit Trail',
    'nav.workflow': 'Workflow',
    'nav.analytics': 'Statistiche',
    'nav.admin': 'Amministrazione',
    'common.generate': 'Genera',
    'common.export': 'Esporta',
    'common.filter': 'Filtra',
    'common.search': 'Cerca',
    'common.save': 'Salva',
    'common.cancel': 'Annulla',
    'common.delete': 'Elimina',
    'common.edit': 'Modifica',
    'common.loading': 'Caricamento...',
    'common.no_results': 'Nessun risultato',
    'locale.it': 'Italiano',
    'locale.en': 'English',
    'locale.de': 'Deutsch',
  },
  en: {
    'nav.overview': 'Overview',
    'nav.qa': 'Regulatory Q&A',
    'nav.gap_analysis': 'Gap Analysis',
    'nav.monitor': 'Change Monitor',
    'nav.cross_framework': 'Cross-Framework',
    'nav.alerts': 'Alerts',
    'nav.reg_feed': 'Regulatory Feed',
    'nav.documents': 'Documents',
    'nav.reports': 'Reports',
    'nav.clients': 'Clients',
    'nav.audit_trail': 'Audit Trail',
    'nav.workflow': 'Workflow',
    'nav.analytics': 'Analytics',
    'nav.admin': 'Administration',
    'common.generate': 'Generate',
    'common.export': 'Export',
    'common.filter': 'Filter',
    'common.search': 'Search',
    'common.save': 'Save',
    'common.cancel': 'Cancel',
    'common.delete': 'Delete',
    'common.edit': 'Edit',
    'common.loading': 'Loading...',
    'common.no_results': 'No results',
    'locale.it': 'Italiano',
    'locale.en': 'English',
    'locale.de': 'Deutsch',
  },
  de: {
    'nav.overview': 'Ubersicht',
    'nav.qa': 'Regulatorische Q&A',
    'nav.gap_analysis': 'Gap-Analyse',
    'nav.monitor': 'Anderungsmonitor',
    'nav.cross_framework': 'Cross-Framework',
    'nav.alerts': 'Warnungen',
    'nav.reg_feed': 'Regulatorischer Feed',
    'nav.documents': 'Dokumente',
    'nav.reports': 'Berichte',
    'nav.clients': 'Kunden',
    'nav.audit_trail': 'Prufprotokoll',
    'nav.workflow': 'Workflow',
    'nav.analytics': 'Analytik',
    'nav.admin': 'Verwaltung',
    'common.generate': 'Generieren',
    'common.export': 'Exportieren',
    'common.filter': 'Filtern',
    'common.search': 'Suchen',
    'common.save': 'Speichern',
    'common.cancel': 'Abbrechen',
    'common.delete': 'Loschen',
    'common.edit': 'Bearbeiten',
    'common.loading': 'Wird geladen...',
    'common.no_results': 'Keine Ergebnisse',
    'locale.it': 'Italiano',
    'locale.en': 'English',
    'locale.de': 'Deutsch',
  },
}

const LocaleContext = createContext<LocaleContextType | null>(null)

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    if (typeof window === 'undefined') return 'it'
    return (localStorage.getItem(LOCALE_KEY) as Locale) || 'it'
  })

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l)
    localStorage.setItem(LOCALE_KEY, l)
  }, [])

  const t = useCallback((key: string): string => {
    return translations[locale]?.[key] || translations.it[key] || key
  }, [locale])

  return (
    <LocaleContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </LocaleContext.Provider>
  )
}

export function useLocale() {
  const ctx = useContext(LocaleContext)
  if (!ctx) throw new Error('useLocale must be used within LocaleProvider')
  return ctx
}
