import { useTranslations } from 'next-intl'

/**
 * Who runs NormaAI: the identity sentence, the contact address and, only when
 * one is configured, the VAT number. Nothing here is invented: the VAT line
 * is rendered only if NEXT_PUBLIC_VAT_NUMBER is set for the build.
 */
const VAT_NUMBER = (process.env.NEXT_PUBLIC_VAT_NUMBER ?? '').trim()

export function Imprint({ className }: { className?: string }) {
  const t = useTranslations('site.imprint')
  return (
    <address className={className} style={{ fontStyle: 'normal' }}>
      <span className="block">{t('identity')}</span>
      <span className="block">
        {t.rich('contact', {
          mail: (chunks) => (
            <a href="mailto:info@normaai.org" className="text-union underline hover:no-underline">
              {chunks}
            </a>
          ),
        })}
      </span>
      {VAT_NUMBER && <span className="block tabular">{t('vat', { vat: VAT_NUMBER })}</span>}
    </address>
  )
}
