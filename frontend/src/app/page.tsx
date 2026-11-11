import Link from 'next/link'
import { CheckCircle2 } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import { SiteHeader } from '@/components/site/SiteHeader'
import { SiteFooter } from '@/components/site/SiteFooter'
import { CodexForm } from '@/components/site/CodexForm'
import { AnswerExample } from '@/components/landing/AnswerExample'
import { DocumentCheckExample } from '@/components/landing/DocumentCheckExample'
import { ProvisionChangeExample } from '@/components/landing/ProvisionChangeExample'
import { ButtonLink } from '@/components/ui/Button'
import { FrameworkBadge } from '@/components/ui/Badge'
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table'
import { itemKeys } from '@/components/LegalLayout'
import { eurlexLang } from '@/i18n/config'
import { cn } from '@/lib/cn'
import { CORPUS_ACTS, CORPUS_AREAS, actsOf, corpusActName } from '@/lib/corpus-acts'
import { eurlexUrl } from '@/lib/sources'

// Public landing page. It opens with the document check, the thing NormaAI
// does that a general assistant does not: checking the legal references of a
// document against the official text and saying when a cited provision
// changes. Asking questions and the scope checks follow.
//
// Every claim must be true of the code as it ships (DESIGN.md, "stati
// onesti"). The sections say what each capability checks and on which text;
// what a visitor cannot reach yet is said once, in the dated status line of
// the hero (`landing.hero.status`): update that line when it changes.

/** The two actions that work today: the demo with sample data, and an email for a pilot. */
function Actions({ className }: { className?: string }) {
  const t = useTranslations('landing.cta')
  return (
    <div className={cn('flex flex-wrap gap-3', className)}>
      <ButtonLink href="/demo" size="lg">
        {t('tryDemo')}
      </ButtonLink>
      <ButtonLink href={t('mailto')} variant="secondary" size="lg">
        {t('pilot')}
      </ButtonLink>
    </div>
  )
}

/**
 * The acts of the question-and-answer corpus, by area, each linked to its
 * text on EUR-Lex. On a narrow screen the area moves above its acts, so the
 * names of the acts keep the whole width.
 */
function CorpusTable() {
  const t = useTranslations()
  const lang = eurlexLang(useLocale())
  return (
    <Table>
      <THead>
        <TR>
          <TH className="hidden sm:table-cell">{t('landing.sources.qa.colArea')}</TH>
          <TH>{t('landing.sources.qa.colActs')}</TH>
        </TR>
      </THead>
      <TBody>
        {CORPUS_AREAS.map((area) => (
          <TR key={area}>
            <TD className="hidden whitespace-nowrap sm:table-cell">
              <FrameworkBadge framework={area} />
            </TD>
            <TD>
              <FrameworkBadge framework={area} className="mb-2 sm:hidden" />
              <ul className="space-y-1.5">
                {actsOf(area).map((act) => (
                  <li key={act.celex}>
                    <a
                      href={eurlexUrl(act.celex, lang)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-serif text-read text-union hover:underline"
                    >
                      {corpusActName(act, t)}
                    </a>
                    <span className="block text-small text-ink-2 sm:inline">
                      <span className="hidden sm:inline">, </span>
                      {t(`landing.sources.acts.${act.celex}`)}
                    </span>
                  </li>
                ))}
              </ul>
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  )
}

export default function Home() {
  const t = useTranslations('landing')
  const acts = CORPUS_ACTS.length

  return (
    <div className="min-h-screen bg-surface text-ink">
      <SiteHeader />

      <main>
        {/* Hero: the positioning, the two actions, today's status, a checked document */}
        <section className="mx-auto max-w-site px-6 pb-16 pt-12 md:pb-20 md:pt-16">
          <div className="grid gap-12 lg:grid-cols-12 lg:items-start">
            <div className="lg:col-span-6 lg:pt-4">
              <h1 className="text-h1 sm:text-display">{t('hero.title')}</h1>
              <p className="mt-5 max-w-prose text-h4 text-ink md:text-h3">{t('hero.support')}</p>
              <p className="mt-4 max-w-prose text-read text-ink-2">{t('hero.lead')}</p>
              <Actions className="mt-8" />
              <p className="mt-6 max-w-prose border-l-2 border-rule-2 pl-3 text-small text-ink-2">
                {t.rich('hero.status', {
                  b: (chunks) => <span className="font-medium text-ink">{chunks}</span>,
                })}
              </p>
            </div>
            <div className="lg:col-span-6">
              <DocumentCheckExample />
            </div>
          </div>
        </section>

        {/* Check a document: the three checks, what comes out, what it does not do */}
        <section id="come-funziona" className="scroll-mt-16 border-t border-rule">
          <div className="mx-auto max-w-site px-6 py-16 md:py-20">
            <h2 className="max-w-3xl text-h2 md:text-h1">{t('check.title')}</h2>
            <p className="mt-4 max-w-prose text-read text-ink-2">{t('check.lead')}</p>
            <div className="mt-10 grid gap-10 md:grid-cols-3 md:gap-0 md:divide-x md:divide-rule">
              {itemKeys(t.raw('check.items')).map((k) => (
                <div key={k} className="md:px-8 md:first:pl-0 md:last:pr-0">
                  <h3 className="text-h3">{t(`check.items.${k}.title`)}</h3>
                  <p className="mt-3 text-body text-ink-2">{t(`check.items.${k}.body`)}</p>
                </div>
              ))}
            </div>
            <div className="mt-12 grid gap-8 border-t border-rule pt-8 md:grid-cols-2 md:gap-12">
              <div>
                <h3 className="text-h4">{t('check.result.title')}</h3>
                <p className="mt-2 text-body text-ink-2">{t('check.result.body')}</p>
              </div>
              <div>
                <h3 className="text-h4">{t('check.limits.title')}</h3>
                <p className="mt-2 text-body text-ink-2">{t('check.limits.body')}</p>
              </div>
            </div>
          </div>
        </section>

        {/* Watch: the warning when a cited provision changes */}
        <section id="sorveglia" className="scroll-mt-16 border-t border-rule bg-surface-2">
          <div className="mx-auto grid max-w-site gap-10 px-6 py-16 md:py-20 lg:grid-cols-12 lg:gap-12">
            <div className="lg:col-span-5">
              <h2 className="text-h2 md:text-h1">{t('watch.title')}</h2>
              <p className="mt-4 text-read text-ink-2">{t('watch.body')}</p>
              <p className="mt-4 text-read text-ink-2">{t('watch.clients')}</p>
            </div>
            <div className="lg:col-span-7">
              <ProvisionChangeExample />
            </div>
          </div>
        </section>

        {/* Ask: questions answered with the passage of law */}
        <section id="chiedi" className="scroll-mt-16 border-t border-rule">
          <div className="mx-auto grid max-w-site gap-10 px-6 py-16 md:py-20 lg:grid-cols-12 lg:gap-12">
            <div className="lg:col-span-5">
              <h2 className="text-h2 md:text-h1">{t('ask.title')}</h2>
              <p className="mt-4 text-read text-ink-2">{t('ask.body', { acts })}</p>
              <ul className="mt-4 list-disc space-y-1.5 pl-5 text-body text-ink-2 marker:text-ink-3">
                {itemKeys(t.raw('ask.points')).map((k) => (
                  <li key={k}>{t(`ask.points.${k}`)}</li>
                ))}
              </ul>
              <Link href="/metodo" className="mt-6 inline-block text-read font-medium text-union hover:underline">
                {t('ask.method')}
              </Link>
            </div>
            <div className="lg:col-span-7">
              <AnswerExample />
            </div>
          </div>
        </section>

        {/* Scope and deadlines: the free checks, as secondary links */}
        <section id="ambito" className="scroll-mt-16 border-t border-rule">
          <div className="mx-auto grid max-w-site gap-6 px-6 py-12 md:py-14 lg:grid-cols-12 lg:gap-12">
            <div className="lg:col-span-7">
              <h2 className="text-h3 md:text-h2">{t('scope.title')}</h2>
              <p className="mt-3 max-w-prose text-read text-ink-2">{t('scope.body')}</p>
            </div>
            <ul className="space-y-2 text-read lg:col-span-5 lg:pt-1">
              <li>
                <a href="/scope-csrd.html" className="text-union hover:underline">
                  {t('scope.csrd')}
                </a>
              </li>
              <li>
                <a href="/scope-aiact.html" className="text-union hover:underline">
                  {t('scope.aiAct')}
                </a>
              </li>
            </ul>
          </div>
        </section>

        {/* Sources: the corpus of the answers and, apart from it, the texts the document check reads */}
        <section id="fonti" className="scroll-mt-16 border-t border-rule bg-surface-2">
          <div className="mx-auto max-w-site px-6 py-16 md:py-20">
            <h2 className="max-w-3xl text-h2 md:text-h1">{t('sources.title')}</h2>
            <p className="mt-4 max-w-prose text-read text-ink-2">{t('sources.lead')}</p>

            <h3 className="mt-10 text-h3">{t('sources.qa.title', { acts })}</h3>
            <p className="mt-3 max-w-prose text-read text-ink-2">{t('sources.qa.body')}</p>
            <div className="mt-6">
              <CorpusTable />
            </div>

            <h3 className="mt-12 text-h3">{t('sources.check.title')}</h3>
            <dl className="mt-4 grid gap-8 md:grid-cols-2 md:gap-12">
              {(['eu', 'it'] as const).map((k) => (
                <div key={k}>
                  <dt className="font-serif text-h4 font-medium text-ink">{t(`sources.check.${k}.title`)}</dt>
                  <dd className="mt-2 text-read text-ink-2">{t(`sources.check.${k}.body`)}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-10 border-t border-rule pt-6">
              <p className="max-w-prose text-small text-ink-2">{t('sources.authentic')}</p>
            </div>
          </div>
        </section>

        {/* For whom: consultants first */}
        <section className="border-t border-rule">
          <div className="mx-auto max-w-site px-6 py-16 md:py-20">
            <h2 className="max-w-3xl text-h2 md:text-h1">{t('who.title')}</h2>
            <div className="mt-10 grid gap-10 lg:grid-cols-12 lg:gap-12">
              {itemKeys(t.raw('who.items')).map((k, i) => (
                <div key={k} className={i === 0 ? 'lg:col-span-6' : 'lg:col-span-3'}>
                  <h3 className="text-h3">{t(`who.items.${k}.who`)}</h3>
                  <p className="mt-3 max-w-prose text-read text-ink-2">
                    {t(`who.items.${k}.text`, { areas: CORPUS_AREAS.length })}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Codex (the words of this block belong to the Codex stream: `landing.codex`, `site.codexForm`) */}
        <section id="codex" className="scroll-mt-16 border-t border-rule">
          <div className="mx-auto grid max-w-site gap-12 px-6 py-16 md:py-20 lg:grid-cols-12 lg:items-start">
            <div className="lg:col-span-7">
              <p className="text-small text-ink-3">{t('codex.kicker')}</p>
              <h2 className="mt-2 text-h2 md:text-h1">{t('codex.title')}</h2>
              <p className="mt-5 max-w-prose text-read text-ink-2">{t('codex.lead')}</p>
              <ul className="mt-6 space-y-2.5 text-body text-ink-2">
                {itemKeys(t.raw('codex.points')).map((k) => (
                  <li key={k} className="flex items-start gap-2.5">
                    <CheckCircle2 className="mt-1 h-4 w-4 shrink-0 text-ok" aria-hidden="true" />
                    {t(`codex.points.${k}`)}
                  </li>
                ))}
              </ul>
            </div>
            <div className="lg:col-span-5">
              <CodexForm />
            </div>
          </div>
        </section>

        {/* Demo and pilot: the two actions again */}
        <section id="demo" className="scroll-mt-16 border-t border-rule bg-surface-2">
          <div className="mx-auto max-w-site px-6 py-16 md:py-20">
            <h2 className="max-w-3xl text-h2 md:text-h1">{t('demo.title')}</h2>
            <p className="mt-4 max-w-prose text-read text-ink-2">{t('demo.lead')}</p>
            <Actions className="mt-8" />
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  )
}
