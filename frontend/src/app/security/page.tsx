import type { Metadata } from 'next'
import { getFormatter, getTranslations } from 'next-intl/server'
import { LEGAL_TAGS, LegalLayout, LegalSection, itemKeys } from '@/components/LegalLayout'
import { LONG_DATE } from '@/i18n/format'
import { LEGAL_UPDATED_ON } from '@/lib/legal-dates'

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('legal.security')
  return { title: t('title'), description: t('intro') }
}

const REPO = 'https://github.com/Dan23RR/NormaAI'

/** Files of the public repository where a reader can check the claims above. */
async function InCode({ paths }: { paths: string[] }) {
  const t = await getTranslations('legal')
  return (
    <p className="text-small text-ink-3">
      {t('inCode')}
      {paths.map((path, i) => (
        <span key={path}>
          {i > 0 && ', '}
          <a href={`${REPO}/blob/main/${path}`} target="_blank" rel="noopener noreferrer">
            <code className="font-mono">{path}</code>
          </a>
        </span>
      ))}
      .
    </p>
  )
}

export default async function SecurityPage() {
  const t = await getTranslations('legal.security')
  const format = await getFormatter()
  const rich = (key: string) => t.rich(key, LEGAL_TAGS)
  const list = (key: string) => (
    <ul>
      {itemKeys(t.raw(key)).map((k) => (
        <li key={k}>{rich(`${key}.${k}`)}</li>
      ))}
    </ul>
  )

  return (
    <LegalLayout title={t('title')} intro={t('intro')} lastUpdated={format.dateTime(LEGAL_UPDATED_ON, LONG_DATE)}>
      <LegalSection title={t('hosting.title')}>
        <p>{t('hosting.p1')}</p>
        <p>{t('hosting.p2')}</p>
        <InCode
          paths={[
            'frontend/vercel.json',
            'docker-compose.prod.yml',
            'infra/Caddyfile',
            'docker-compose.yml',
            'Dockerfile',
          ]}
        />
      </LegalSection>

      <LegalSection title={t('model.title')}>
        <p>{rich('model.p1')}</p>
        <p>{t('model.p2')}</p>
        <InCode paths={['src/config.py']} />
      </LegalSection>

      <LegalSection title={t('access.title')}>
        {list('access.items')}
        <p>{t('access.p')}</p>
        <InCode
          paths={[
            'src/auth/security.py',
            'src/auth/router.py',
            'src/auth/brute_force.py',
            'src/api/rate_limit.py',
          ]}
        />
      </LegalSection>

      <LegalSection title={t('isolation.title')}>
        <p>{t('isolation.p')}</p>
        {list('isolation.items')}
        <InCode
          paths={[
            'alembic/versions/002_enable_rls_policies.py',
            'scripts/setup_app_role.sql',
            'src/db/engine.py',
            'src/api/lifespan.py',
            'src/cache.py',
            'src/nlp/embedding/indexer.py',
            'tests/test_rls_pool_isolation.py',
          ]}
        />
      </LegalSection>

      <LegalSection title={t('documents.title')}>
        <p>{t('documents.p1')}</p>
        <p>{t('documents.p2')}</p>
        <InCode paths={['src/api/routers/data.py', 'src/api/routers/gdpr.py']} />
      </LegalSection>

      <LegalSection title={t('headers.title')}>
        {list('headers.items')}
        <InCode
          paths={[
            'frontend/src/middleware.ts',
            'frontend/next.config.js',
            'src/api/middleware.py',
            'src/config.py',
            'src/audit.py',
          ]}
        />
      </LegalSection>

      <LegalSection title={t('links.title')}>
        <p>{t('links.p')}</p>
        <InCode paths={['src/api/routers/leads.py']} />
      </LegalSection>

      <LegalSection title={t('audit.title')}>
        <p>{t('audit.p1')}</p>
        <p>{t('audit.p2')}</p>
        <InCode paths={['src/audit.py']} />
      </LegalSection>

      <LegalSection title={t('backup.title')}>
        <p>{rich('backup.p1')}</p>
        <p>{t('backup.p2')}</p>
        <InCode paths={['scripts/backup_postgres.sh', 'docs/BACKUP_STRATEGY.md']} />
      </LegalSection>

      <LegalSection title={t('supplyChain.title')}>
        {list('supplyChain.items')}
        <InCode
          paths={[
            '.github/workflows/ci.yml',
            '.github/workflows/codeql.yml',
            '.github/workflows/release.yml',
            '.github/dependabot.yml',
            'LICENSE',
          ]}
        />
      </LegalSection>

      <LegalSection title={t('missing.title')}>
        {list('missing.items')}
        <InCode paths={['src/agents/sanitization.py', 'SECURITY.md']} />
      </LegalSection>

      <LegalSection title={t('report.title')}>
        <p>{rich('report.p1')}</p>
        {list('report.items')}
        <p>{t('report.p2')}</p>
        <p>{rich('report.p3')}</p>
        <InCode paths={['SECURITY.md', 'docs/legal/DPA_template_clienti.md']} />
      </LegalSection>
    </LegalLayout>
  )
}
