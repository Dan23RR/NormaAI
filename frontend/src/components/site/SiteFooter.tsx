import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { LogoMark, Wordmark } from '@/components/Logo'

const COLUMNS: Array<{ title: string; links: Array<{ href: string; key: string; external?: boolean }> }> = [
  {
    title: 'product',
    links: [
      { href: '/#come-funziona', key: 'ask' },
      { href: '/scope-csrd.html', key: 'scopeCsrd' },
      { href: '/scope-aiact.html', key: 'scopeAiAct' },
      { href: '/#codex', key: 'codex' },
    ],
  },
  {
    title: 'howWeWork',
    links: [
      { href: '/metodo', key: 'method' },
      { href: '/#fonti', key: 'sources' },
      { href: 'https://github.com/Dan23RR/NormaAI', key: 'github', external: true },
    ],
  },
  {
    title: 'legal',
    links: [
      { href: '/privacy', key: 'privacy' },
      { href: '/cookie', key: 'cookie' },
      { href: '/terms', key: 'terms' },
      { href: '/security', key: 'security' },
    ],
  },
]

/** Shared footer of the public pages. */
export function SiteFooter() {
  const t = useTranslations('site.footer')
  return (
    <footer className="border-t border-rule bg-surface-2">
      <div className="mx-auto grid max-w-site gap-10 px-6 py-14 md:grid-cols-12">
        <div className="md:col-span-5">
          <div className="flex items-center gap-2.5">
            <LogoMark size={28} />
            <Wordmark className="text-h3" />
          </div>
          <p className="mt-4 max-w-sm text-small text-ink-2">{t('tagline')}</p>
          <p className="mt-4 text-small text-ink-2">
            <a href="mailto:info@normaai.org" className="text-union hover:underline">
              info@normaai.org
            </a>
          </p>
        </div>
        {COLUMNS.map((col) => (
          <div key={col.title} className="md:col-span-2">
            <h2 className="font-sans text-small font-semibold text-ink">{t(col.title)}</h2>
            <ul className="mt-3 space-y-2">
              {col.links.map((l) =>
                l.external ? (
                  <li key={l.href}>
                    <a
                      href={l.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-small text-ink-2 no-underline hover:text-ink hover:underline"
                    >
                      {t(l.key)}
                    </a>
                  </li>
                ) : l.href.endsWith('.html') ? (
                  <li key={l.href}>
                    <a href={l.href} className="text-small text-ink-2 no-underline hover:text-ink hover:underline">
                      {t(l.key)}
                    </a>
                  </li>
                ) : (
                  <li key={l.href}>
                    <Link href={l.href} className="text-small text-ink-2 no-underline hover:text-ink hover:underline">
                      {t(l.key)}
                    </Link>
                  </li>
                ),
              )}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-rule">
        <div className="mx-auto flex max-w-site flex-col gap-2 px-6 py-5 text-caption text-ink-3 md:flex-row md:items-center md:justify-between">
          <p>{t('credits', { year: String(new Date().getFullYear()) })}</p>
          <p>{t('aiNotice')}</p>
        </div>
      </div>
    </footer>
  )
}
