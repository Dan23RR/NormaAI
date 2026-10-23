import Link from 'next/link'
import { LogoMark, Wordmark } from '@/components/Logo'

const columns: Array<{ title: string; links: Array<{ href: string; label: string; external?: boolean }> }> = [
  {
    title: 'Prodotto',
    links: [
      { href: '/#come-funziona', label: 'Chiedi' },
      { href: '/scope-csrd.html', label: 'Verifica ambito CSRD' },
      { href: '/scope-aiact.html', label: 'Verifica AI Act, art. 50' },
      { href: '/#codex', label: 'Codex Post-Omnibus' },
    ],
  },
  {
    title: 'Come lavoriamo',
    links: [
      { href: '/metodo', label: 'Metodo' },
      { href: '/#fonti', label: 'Fonti' },
      { href: 'https://github.com/Dan23RR/NormaAI', label: 'Codice su GitHub', external: true },
    ],
  },
  {
    title: 'Legale',
    links: [
      { href: '/privacy', label: 'Privacy' },
      { href: '/cookie', label: 'Cookie' },
      { href: '/terms', label: 'Termini' },
      { href: '/security', label: 'Sicurezza' },
    ],
  },
]

/** Shared footer of the public pages. */
export function SiteFooter() {
  return (
    <footer className="border-t border-rule bg-surface-2">
      <div className="mx-auto grid max-w-site gap-10 px-6 py-14 md:grid-cols-12">
        <div className="md:col-span-5">
          <div className="flex items-center gap-2.5">
            <LogoMark size={28} />
            <Wordmark className="text-h3" />
          </div>
          <p className="mt-4 max-w-sm text-small text-ink-2">
            Risposte sul diritto dell'Unione con la fonte esatta: atto, articolo, passaggio di legge
            e link al testo ufficiale. Quando il testo non basta, lo diciamo.
          </p>
          <p className="mt-4 text-small text-ink-2">
            <a href="mailto:info@normaai.org" className="text-union hover:underline">
              info@normaai.org
            </a>
          </p>
        </div>
        {columns.map((col) => (
          <div key={col.title} className="md:col-span-2">
            <h2 className="font-sans text-small font-semibold text-ink">{col.title}</h2>
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
                      {l.label}
                    </a>
                  </li>
                ) : (
                  <li key={l.href}>
                    <Link href={l.href} className="text-small text-ink-2 no-underline hover:text-ink hover:underline">
                      {l.label}
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
          <p>NormaAI è un progetto di Daniel Culotta, Inverigo (CO), Italia. © {new Date().getFullYear()}</p>
          <p>
            Le risposte sono generate da un sistema di intelligenza artificiale e non sostituiscono la
            consulenza di un professionista.
          </p>
        </div>
      </div>
    </footer>
  )
}
