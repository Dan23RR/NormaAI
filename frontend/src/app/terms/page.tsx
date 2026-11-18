import type { Metadata } from 'next'
import { getFormatter, getTranslations } from 'next-intl/server'
import { LEGAL_TAGS, LegalLayout, LegalSection, itemKeys } from '@/components/LegalLayout'
import { Imprint } from '@/components/site/Imprint'
import { LONG_DATE } from '@/i18n/format'
import { LEGAL_UPDATED_ON } from '@/lib/legal-dates'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('legal.terms')
  return { title: t('title'), description: t('intro') }
}

// LAWYER REVIEW REQUIRED before the service is offered beyond the free pilot.
// The wording of `legal.terms` (messages/it.json, en.json) corrects what was
// void or false on 2026-11-18: a blanket exclusion of liability (void for
// wilful misconduct and gross negligence, art. 1229 c.c.), a cap equal to the
// fees of a free service, no provider, price, duration, law or court. It is
// not legal advice. Open points for the lawyer:
// - the provider is the identity already public on the site (site.imprint:
//   Daniel Culotta, natural person, Inverigo). [GAP: update it, and add the VAT
//   number and any company, before the first invoice.]
// - clauses that limit liability, allow withdrawal or end the pilot, or set a
//   court are "clausole vessatorie" in standard terms: with professionals they
//   must be approved specifically in writing (artt. 1341-1342 c.c.). There is
//   no UI for that separate approval today: it has to be collected apart.
// - with consumers: art. 33 and art. 66-bis of the Codice del consumo, the
//   one-sided "Modifiche" clause, and whether a liability cap for professionals
//   is wanted at all.
export default async function TermsPage() {
  const t = await getTranslations('legal.terms')
  const ti = await getTranslations('site.imprint')
  const format = await getFormatter()
  const rich = (key: string) => t.rich(key, LEGAL_TAGS)

  return (
    <LegalLayout title={t('title')} intro={t('intro')} lastUpdated={format.dateTime(LEGAL_UPDATED_ON, LONG_DATE)}>
      <LegalSection title={t('nature.title')}>
        {/* The imprint: who runs the service, how to reach them and, when one
            is configured for the build, the VAT number. */}
        <div className="rounded-md border border-rule bg-surface-2 px-4 py-3">
          <h3 className="font-sans text-small font-semibold text-ink">{ti('title')}</h3>
          <Imprint className="mt-1 space-y-1 text-body text-ink-2" />
        </div>
        {itemKeys(t.raw('nature.p')).map((k) => (
          <p key={k}>{rich(`nature.p.${k}`)}</p>
        ))}
      </LegalSection>

      <LegalSection title={t('pilot.title')}>
        {itemKeys(t.raw('pilot.p')).map((k) => (
          <p key={k}>{rich(`pilot.p.${k}`)}</p>
        ))}
      </LegalSection>

      <LegalSection title={t('ai.title')}>
        <p>{t('ai.intro')}</p>
        <ul>
          {itemKeys(t.raw('ai.items')).map((k) => (
            <li key={k}>{rich(`ai.items.${k}`)}</li>
          ))}
        </ul>
        <p>{t('ai.p')}</p>
      </LegalSection>

      <LegalSection title={t('liability.title')}>
        {itemKeys(t.raw('liability.p')).map((k) => (
          <p key={k}>{rich(`liability.p.${k}`)}</p>
        ))}
      </LegalSection>

      <LegalSection title={t('warranty.title')}>
        <p>{t('warranty.p')}</p>
      </LegalSection>

      <LegalSection title={t('updates.title')}>
        <p>{t('updates.p')}</p>
      </LegalSection>

      <LegalSection title={t('data.title')}>
        <p>{rich('data.p')}</p>
      </LegalSection>

      <LegalSection title={t('source.title')}>
        <p>{rich('source.p')}</p>
      </LegalSection>

      <LegalSection title={t('law.title')}>
        {itemKeys(t.raw('law.p')).map((k) => (
          <p key={k}>{rich(`law.p.${k}`)}</p>
        ))}
      </LegalSection>

      <LegalSection title={t('changes.title')}>
        <p>{t('changes.p')}</p>
      </LegalSection>
    </LegalLayout>
  )
}
