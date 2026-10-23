import type { Metadata } from 'next'
import { getTranslations } from 'next-intl/server'
import { SiteHeader } from '@/components/site/SiteHeader'
import { SiteFooter } from '@/components/site/SiteFooter'
import { ButtonLink } from '@/components/ui/Button'
import { LEGAL_TAGS, itemKeys } from '@/components/LegalLayout'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('legal.metodo')
  return { title: t('metaTitle'), description: t('metaDescription') }
}

const REPO = 'https://github.com/Dan23RR/NormaAI'

/** Files of the public repository where a reader can check the claims above. */
async function InCode({ paths }: { paths: string[] }) {
  const t = await getTranslations('legal')
  return (
    <p className="mt-4 text-small text-ink-3">
      {t('inCode')}
      {paths.map((path, i) => (
        <span key={path}>
          {i > 0 && ', '}
          <a
            href={`${REPO}/blob/main/${path}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-union hover:underline"
          >
            <code className="font-mono">{path}</code>
          </a>
        </span>
      ))}
      .
    </p>
  )
}

// Acts in the acquisition list (CORE_FRAMEWORKS in src/crawler/eurlex/client.py):
// the words live in `legal.metodo.corpus.frameworks`.

/** The repository files behind each pipeline step, in the order of `legal.metodo.pipeline.steps`. */
const PIPELINE_PATHS: string[][] = [
  ['src/nlp/embedding/indexer.py', 'src/config.py'],
  ['src/agents/nodes.py', 'prompts/qa_bot.txt', 'src/agents/sanitization.py'],
  ['src/agents/snc_node.py', 'src/agents/snc_layer.py', 'src/config.py'],
  ['src/agents/nodes.py', 'src/agents/snc_node.py'],
  ['src/config.py', 'src/agents/graph.py', 'src/agents/cove/orchestrator.py'],
  [],
]

/** The repository files behind each documented choice, in the order of `legal.metodo.choices.items`. */
const CHOICE_PATHS: string[][] = [
  ['src/config.py'],
  ['src/config.py', 'src/api/routers/intelligence.py', 'src/reports/generator.py'],
  ['src/config.py', 'src/api/lifespan.py'],
  ['src/config.py', 'src/agents/graph.py'],
  ['src/crawler/eurlex/client.py'],
]

export default async function MetodoPage() {
  const t = await getTranslations('legal.metodo')
  const rich = (key: string) => t.rich(key, { ...LEGAL_TAGS, code: (chunks) => <code className="font-mono text-small">{chunks}</code> })

  return (
    <div className="min-h-screen bg-surface text-ink">
      <SiteHeader />

      <main>
        <section className="mx-auto max-w-site px-6 pb-14 pt-14 md:pt-20">
          <div className="max-w-prose">
            <h1 className="text-h1 md:text-display">{t('title')}</h1>
            <p className="mt-5 text-read text-ink-2">{t('intro')}</p>
          </div>
        </section>

        <section className="border-t border-rule">
          <div className="mx-auto max-w-site px-6 py-14">
            <h2 className="text-h2">{t('corpus.title')}</h2>
            <div className="mt-5 max-w-prose space-y-4 text-read text-ink-2">
              <p>{t('corpus.p1')}</p>
              <p>{t('corpus.p2')}</p>
              <ul className="list-disc space-y-1.5 pl-6">
                {itemKeys(t.raw('corpus.frameworks')).map((k) => (
                  <li key={k}>
                    <strong className="font-semibold text-ink">{t(`corpus.frameworks.${k}.name`)}</strong>: {t(`corpus.frameworks.${k}.acts`)}
                  </li>
                ))}
              </ul>
              <p>{rich('corpus.p3')}</p>
            </div>
            <InCode
              paths={[
                'src/crawler/eurlex/client.py',
                'src/crawler/normattiva/client.py',
                'src/config.py',
                'src/nlp/embedding/indexer.py',
              ]}
            />
          </div>
        </section>

        <section className="border-t border-rule">
          <div className="mx-auto max-w-site px-6 py-14">
            <h2 className="text-h2">{t('pipeline.title')}</h2>
            <p className="mt-5 max-w-prose text-read text-ink-2">{t('pipeline.lead')}</p>
            <ol className="mt-8 max-w-prose list-decimal space-y-8 pl-6">
              {itemKeys(t.raw('pipeline.steps')).map((k, i) => (
                <li key={k}>
                  <h3 className="text-h3">{t(`pipeline.steps.${k}.title`)}</h3>
                  <p className="mt-2 text-read text-ink-2">{t(`pipeline.steps.${k}.body`)}</p>
                  {(PIPELINE_PATHS[i]?.length ?? 0) > 0 && <InCode paths={PIPELINE_PATHS[i]} />}
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="border-t border-rule">
          <div className="mx-auto max-w-site px-6 py-14">
            <h2 className="text-h2">{t('reader.title')}</h2>
            <ul className="mt-5 max-w-prose list-disc space-y-2 pl-6 text-read text-ink-2">
              {itemKeys(t.raw('reader.items')).map((k) => (
                <li key={k}>{t(`reader.items.${k}`)}</li>
              ))}
            </ul>
            <InCode
              paths={[
                'frontend/src/components/chiedi/AiNotice.tsx',
                'frontend/src/components/app/AppShell.tsx',
                'src/reports/generator.py',
              ]}
            />
          </div>
        </section>

        <section className="border-t border-rule">
          <div className="mx-auto max-w-site px-6 py-14">
            <h2 className="text-h2">{t('data.title')}</h2>
            <div className="mt-5 max-w-prose space-y-4 text-read text-ink-2">
              <p>{t('data.p1')}</p>
              <p>
                {t.rich('data.p2', {
                  securityPage: (chunks) => (
                    <a href="/security" className="text-union hover:underline">
                      {chunks}
                    </a>
                  ),
                })}
              </p>
            </div>
          </div>
        </section>

        <section className="border-t border-rule">
          <div className="mx-auto max-w-site px-6 py-14">
            <h2 className="text-h2">{t('ci.title')}</h2>
            <div className="mt-5 max-w-prose space-y-4 text-read text-ink-2">
              <p>{t('ci.p1')}</p>
              <p>{t('ci.p2')}</p>
            </div>
            <InCode
              paths={[
                '.github/workflows/ci.yml',
                '.github/workflows/codeql.yml',
                'tests/test_rls_pool_isolation.py',
              ]}
            />
          </div>
        </section>

        <section className="border-t border-rule">
          <div className="mx-auto max-w-site px-6 py-14">
            <h2 className="text-h2">{t('choices.title')}</h2>
            <p className="mt-5 max-w-prose text-read text-ink-2">{t('choices.lead')}</p>
            <ul className="mt-8 max-w-prose space-y-8">
              {itemKeys(t.raw('choices.items')).map((k, i) => (
                <li key={k} className="border-t border-rule pt-6">
                  <h3 className="text-h3">{t(`choices.items.${k}.title`)}</h3>
                  <p className="mt-2 text-read text-ink-2">{t(`choices.items.${k}.body`)}</p>
                  <InCode paths={CHOICE_PATHS[i] ?? []} />
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="border-t border-rule bg-surface-2">
          <div className="mx-auto max-w-site px-6 py-14">
            <h2 className="text-h2">{t('cta.title')}</h2>
            <p className="mt-4 max-w-prose text-read text-ink-2">{t('cta.lead')}</p>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <ButtonLink href="mailto:info@normaai.org?subject=NormaAI%20demo">{t('cta.demo')}</ButtonLink>
              <ButtonLink href="/#codex" variant="secondary">
                {t('cta.codex')}
              </ButtonLink>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  )
}
