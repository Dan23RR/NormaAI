import Link from 'next/link'
import { CheckCircle2 } from 'lucide-react'
import { getFormatter, getLocale, getTranslations } from 'next-intl/server'
import { SiteHeader } from '@/components/site/SiteHeader'
import { SiteFooter } from '@/components/site/SiteFooter'
import { CodexForm } from '@/components/site/CodexForm'
import { ButtonLink } from '@/components/ui/Button'
import { Badge, FrameworkBadge } from '@/components/ui/Badge'
import { LawQuote } from '@/components/ui/LawQuote'
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table'
import { itemKeys } from '@/components/LegalLayout'
import { eurlexLang } from '@/i18n/config'
import { LONG_DATE } from '@/i18n/format'
import { AI_ACT_ART_50_1_IT } from '@/lib/law-passages'
import { eurlexUrl } from '@/lib/sources'

// Public landing page. Every claim here must be true of the code as it ships
// (see DESIGN.md, "stati onesti"). The hero shows the product's signature
// element: an answer with the passage of law that supports it.

const ACT_ROWS = ['CSRD', 'CSDDD', 'AI_ACT', 'NIS2', 'DORA', 'GDPR', 'TAXONOMY', 'CRA', 'ESRS'] as const

/** 2 August 2026: application of Article 50 of the AI Act (Art. 113). */
const ART_50_APPLIES = new Date(Date.UTC(2026, 7, 2))

async function AnswerExample() {
  const t = await getTranslations('landing.example')
  const tu = await getTranslations('ui')
  const format = await getFormatter()
  const locale = await getLocale()
  const date = format.dateTime(ART_50_APPLIES, LONG_DATE)
  const ref = (id: string) => (chunks: React.ReactNode) => (
    <a href={`#${id}`} className="font-medium text-union">
      {chunks}
    </a>
  )
  return (
    <figure className="rounded-xl border border-rule bg-surface shadow-doc">
      <figcaption className="flex items-center justify-between border-b border-rule px-5 py-3 text-caption text-ink-3">
        <span>{t('caption')}</span>
        <span>{t('sourceCaption')}</span>
      </figcaption>
      <div className="px-5 py-5">
        <p className="text-small text-ink-3">{t('questionLabel')}</p>
        <p className="mt-1 text-read text-ink">{t('question')}</p>
        <p className="mt-5 text-small text-ink-3">{t('answerLabel')}</p>
        <p className="mt-1 text-read text-ink">
          {t.rich('answer', { date, ref1: ref('esempio-fonte-1'), ref2: ref('esempio-fonte-2') })}
        </p>
        <div className="mt-5 space-y-4 border-t border-rule pt-5">
          <div id="esempio-fonte-1">
            <LawQuote
              quote={AI_ACT_ART_50_1_IT.quote}
              before={AI_ACT_ART_50_1_IT.before}
              after={AI_ACT_ART_50_1_IT.after}
              lang={AI_ACT_ART_50_1_IT.lang}
              act={tu('acts.AI_ACT')}
              article={t('article1')}
              celex={AI_ACT_ART_50_1_IT.celex}
              url={eurlexUrl(AI_ACT_ART_50_1_IT.celex, eurlexLang(locale))}
              origin="EUR-Lex"
            />
          </div>
          <p id="esempio-fonte-2" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small text-ink-2">
            <span>
              <span className="font-medium text-ink">{tu('acts.AI_ACT')}</span>, {t('article2')}
            </span>
            <span className="inline-flex items-center gap-1 text-ok">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              {tu('sourceStatus.verified.short')}
            </span>
            <span>{t('appliesFrom', { date })}</span>
          </p>
        </div>
      </div>
    </figure>
  )
}

export default async function Home() {
  const t = await getTranslations('landing')

  return (
    <div className="min-h-screen bg-surface text-ink">
      <SiteHeader />

      {/* Hero */}
      <section className="mx-auto max-w-site px-6 pb-20 pt-14 md:pt-20">
        <div className="grid gap-12 lg:grid-cols-12 lg:items-start">
          <div className="lg:col-span-6 lg:pt-6">
            <h1 className="text-display md:text-display-lg">{t('hero.title')}</h1>
            <p className="mt-6 max-w-prose text-read text-ink-2 md:text-h4 md:font-normal">{t('hero.lead')}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonLink href="#demo" size="lg">
                {t('hero.requestDemo')}
              </ButtonLink>
              <ButtonLink href="/scope-csrd.html" variant="secondary" size="lg">
                {t('hero.checkScope')}
              </ButtonLink>
            </div>
            <p className="mt-5 text-small text-ink-3">{t('hero.note')}</p>
          </div>
          <div className="lg:col-span-6">
            <AnswerExample />
          </div>
        </div>
      </section>

      {/* Come funziona */}
      <section id="come-funziona" className="border-t border-rule">
        <div className="mx-auto max-w-site px-6 py-20">
          <h2 className="max-w-3xl text-h1 md:text-display">{t('how.title')}</h2>
          <div className="mt-12 grid gap-10 md:grid-cols-3 md:gap-0 md:divide-x md:divide-rule">
            <div className="md:pr-8">
              <h3 className="text-h3">{t('how.ask.title')}</h3>
              <p className="mt-3 text-body text-ink-2">{t('how.ask.body')}</p>
              <ul className="mt-4 space-y-1.5 text-small text-ink-2">
                {itemKeys(t.raw('how.ask.points')).map((k) => (
                  <li key={k}>{t(`how.ask.points.${k}`)}</li>
                ))}
              </ul>
            </div>
            <div className="md:px-8">
              <h3 className="text-h3">{t('how.scope.title')}</h3>
              <p className="mt-3 text-body text-ink-2">{t('how.scope.body')}</p>
              <ul className="mt-4 space-y-1.5 text-small">
                <li>
                  <Link href="/scope-csrd.html" className="text-union hover:underline">
                    {t('how.scope.csrd')}
                  </Link>
                </li>
                <li>
                  <Link href="/scope-aiact.html" className="text-union hover:underline">
                    {t('how.scope.aiAct')}
                  </Link>
                </li>
              </ul>
            </div>
            <div className="md:pl-8">
              <div className="flex items-center gap-2">
                <h3 className="text-h3">{t('how.monitor.title')}</h3>
                <Badge tone="warn">{t('how.monitor.badge')}</Badge>
              </div>
              <p className="mt-3 text-body text-ink-2">{t('how.monitor.body')}</p>
            </div>
          </div>
        </div>
      </section>

      {/* Fonti */}
      <section id="fonti" className="border-t border-rule bg-surface-2">
        <div className="mx-auto max-w-site px-6 py-20">
          <div className="max-w-3xl">
            <h2 className="text-h1 md:text-display">{t('sources.title')}</h2>
            <p className="mt-5 text-read text-ink-2">{t('sources.lead')}</p>
          </div>
          <div className="mt-10">
            <Table>
              <THead>
                <TR>
                  <TH>{t('sources.colScope')}</TH>
                  <TH>{t('sources.colActs')}</TH>
                  <TH className="hidden md:table-cell">{t('sources.colCovers')}</TH>
                </TR>
              </THead>
              <TBody>
                {ACT_ROWS.map((framework) => (
                  <TR key={framework}>
                    <TD className="whitespace-nowrap">
                      <FrameworkBadge framework={framework} />
                    </TD>
                    <TD>
                      <span className="font-serif text-read">{t(`sources.rows.${framework}.act`)}</span>
                      <span className="mt-1 block text-small text-ink-2 md:hidden">{t(`sources.rows.${framework}.covers`)}</span>
                    </TD>
                    <TD className="hidden text-ink-2 md:table-cell">{t(`sources.rows.${framework}.covers`)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>
        </div>
      </section>

      {/* Metodo */}
      <section className="border-t border-rule">
        <div className="mx-auto grid max-w-site gap-12 px-6 py-20 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <h2 className="text-h1 md:text-display">{t('method.title')}</h2>
            <p className="mt-5 text-read text-ink-2">{t('method.lead')}</p>
            <Link href="/metodo" className="mt-6 inline-block text-body font-medium text-union hover:underline">
              {t('method.link')}
            </Link>
          </div>
          <ol className="space-y-6 lg:col-span-7">
            {itemKeys(t.raw('method.steps')).map((k, i) => (
              <li key={k} className="flex gap-5">
                <span className="mt-0.5 font-serif text-h2 tabular text-ink-3" aria-hidden="true">
                  {i + 1}
                </span>
                <div>
                  <h3 className="text-h3">{t(`method.steps.${k}.title`)}</h3>
                  <p className="mt-2 text-body text-ink-2">{t(`method.steps.${k}.body`)}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Per chi */}
      <section className="border-t border-rule bg-surface-2">
        <div className="mx-auto max-w-site px-6 py-20">
          <h2 className="max-w-3xl text-h1 md:text-display">{t('who.title')}</h2>
          <div className="mt-12 grid gap-10 md:grid-cols-3">
            {itemKeys(t.raw('who.items')).map((k) => (
              <div key={k}>
                <h3 className="text-h3">{t(`who.items.${k}.who`)}</h3>
                <p className="mt-3 text-body text-ink-2">{t(`who.items.${k}.text`)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Codex */}
      <section id="codex" className="border-t border-rule">
        <div className="mx-auto grid max-w-site gap-12 px-6 py-20 lg:grid-cols-12 lg:items-start">
          <div className="lg:col-span-7">
            <p className="text-small text-ink-3">{t('codex.kicker')}</p>
            <h2 className="mt-2 text-h1 md:text-display">{t('codex.title')}</h2>
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

      {/* Demo */}
      <section id="demo" className="bg-[#0C1B33] text-[#E8ECF3]">
        <div className="mx-auto max-w-3xl px-6 py-24 text-center">
          <h2 className="text-h1 text-white md:text-display">{t('demo.title')}</h2>
          <p className="mx-auto mt-5 max-w-xl text-read text-[#B3BCCB]">{t('demo.lead')}</p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a
              href={t('demo.mailto')}
              className="inline-flex h-12 items-center justify-center rounded-md bg-white px-6 text-read font-medium text-[#0C1B33] no-underline transition-colors hover:bg-[#E8ECF3]"
            >
              {t('demo.mail')}
            </a>
            <Link
              href="/login"
              className="inline-flex h-12 items-center justify-center rounded-md border border-white/30 px-6 text-read font-medium text-white no-underline transition-colors hover:border-white/60"
            >
              {t('demo.login')}
            </Link>
          </div>
        </div>
      </section>

      <SiteFooter />
    </div>
  )
}
