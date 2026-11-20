import type { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, ExternalLink } from 'lucide-react'
import { useFormatter, useLocale, useTranslations } from 'next-intl'
import { eurlexLang, languageOf } from '@/i18n/config'
import { LONG_DATE, isoToUtcDate } from '@/i18n/format'
import { CHECKED_NOTE, EXAMPLES_CHECKED_ON, GDPR_IN_FORCE, splitAtWord } from '@/lib/landing-examples'
import { eurlexUrl } from '@/lib/sources'

/** A reference as the note writes it, with the number of its outcome below. */
function Reference({ n, label, children }: { n: number; label: string; children: ReactNode }) {
  return (
    <>
      <span className="underline decoration-rule-2 decoration-1 underline-offset-4">{children}</span>{' '}
      <a href={`#esempio-esito-${n}`} aria-label={label} className="font-medium tabular text-union">
        [{n}]
      </a>
    </>
  )
}

/**
 * The document in the hero: an invented client note and what the document
 * check returned for it (src/lib/landing-examples.ts has the record). One
 * quote was found word for word; the other says "48" where Article 33(1) of
 * Regulation (EU) 2016/679 says "72".
 *
 * The highlighter stays behind the official wording only (DESIGN.md): the
 * words of the note, wrong or right, never get it.
 */
export function DocumentCheckExample() {
  const t = useTranslations('landing.example')
  const tu = useTranslations('ui')
  const format = useFormatter()
  const locale = useLocale()
  const language = languageOf(locale)
  const note = CHECKED_NOTE[language]
  const [open, close] = note.marks
  const { quoted, official } = note.altered.difference

  const longDate = (iso: string) => {
    const date = isoToUtcDate(iso)
    return date ? format.dateTime(date, LONG_DATE) : iso
  }
  // The same sentence twice, cut around the one word that differs.
  const inNote = splitAtWord(note.altered.quote, quoted) ?? { before: note.altered.quote, word: '', after: '' }
  const inLaw = splitAtWord(note.altered.official, official) ?? { before: note.altered.official, word: '', after: '' }
  const act = tu('acts.GDPR')
  const url = eurlexUrl(GDPR_IN_FORCE.celex, eurlexLang(locale))

  return (
    <figure aria-label={t('label')} className="rounded-xl border border-rule bg-surface shadow-doc">
      <figcaption className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-rule px-5 py-3 text-caption text-ink-3">
        <span>{t('caption')}</span>
        <span>{t('checkedOn', { date: longDate(EXAMPLES_CHECKED_ON) })}</span>
      </figcaption>

      <div className="px-5 py-5">
        <p className="text-small text-ink-3">{t('inDocument')}</p>
        <div lang={language} className="mt-2 space-y-3 text-read text-ink">
          <p className="font-medium">{note.title}</p>
          <p>
            {note.altered.before}
            <Reference n={1} label={t('toFinding', { n: 1 })}>
              {note.altered.reference}
            </Reference>
            {note.altered.between}
            {open}
            {inNote.before}
            <span className="font-semibold text-bad underline decoration-bad decoration-wavy underline-offset-4">
              {inNote.word}
            </span>
            {inNote.after}
            {close}
            {note.altered.after}
          </p>
          <p>
            {note.verified.before}
            {open}
            {note.verified.quote}
            {close}
            {note.verified.between}
            <Reference n={2} label={t('toFinding', { n: 2 })}>
              {note.verified.reference}
            </Reference>
            {note.verified.after}
          </p>
        </div>

        <div className="mt-5 border-t border-rule pt-5">
          <p className="text-small text-ink-3">{t('outcome', { fix: 1, ok: 1 })}</p>
          <ol className="mt-3 space-y-5">
            <li id="esempio-esito-1" className="scroll-mt-24">
              <p className="flex items-start gap-2 text-small font-medium text-bad">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>
                  <span className="tabular">[1]</span> {t('altered')}
                </span>
              </p>
              <p className="mt-1 pl-6 text-small text-ink-2">{t('difference', { quoted, official })}</p>
              <figure className="ml-6 mt-3 border-l-2 border-mark-deep pl-4">
                <blockquote className="font-serif text-read leading-relaxed text-ink" lang={language} cite={url}>
                  <mark>
                    {inLaw.before}
                    <strong className="font-semibold">{inLaw.word}</strong>
                    {inLaw.after}
                  </mark>
                </blockquote>
                <figcaption className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-small text-ink-2">
                  <span>
                    <span className="font-medium text-ink">{act}</span>, {t('article1')}
                  </span>
                  <span>{t('inForce', { date: longDate(GDPR_IN_FORCE.asOf ?? '') })}</span>
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-union hover:underline"
                  >
                    EUR-Lex
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                </figcaption>
              </figure>
            </li>
            <li id="esempio-esito-2" className="scroll-mt-24">
              <p className="flex items-start gap-2 text-small font-medium text-ok">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>
                  <span className="tabular">[2]</span> {t('verified')}
                </span>
              </p>
              <p className="mt-1 pl-6 text-small text-ink-2">{t('verifiedNote', { act, article: t('article5') })}</p>
            </li>
          </ol>
        </div>
      </div>
    </figure>
  )
}
