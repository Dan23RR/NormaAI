'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { api } from '@/lib/api'
import { getAccessToken, isDemoMode } from '@/lib/auth'
import type { ApiResponse, CompanyProfile } from '@/lib/types'
import { useSSEStream, type CitationEvent, type DoneStats } from '@/hooks/useSSEStream'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Field'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageHeader } from '@/components/ui/PageHeader'
import { useToast } from '@/components/ui/Toast'
import { itemKeys } from '@/components/LegalLayout'
import CompanyProfileForm, { useCompanyProfile } from '@/components/CompanyProfileForm'
import { languageOf } from '@/i18n/config'
import { useErrorText } from '@/i18n/errors'
import { formatCorpusDate } from '@/i18n/format'
import { useTextContext } from '@/i18n/useTextContext'
import { copyToClipboard } from '@/lib/chiedi/copy'
import { corpusDateFrom } from '@/lib/chiedi/dates'
import { phaseLabel } from '@/lib/chiedi/phases'
import { citationsToSources, sseCitationToChiedi } from '@/lib/chiedi/sources'
import { clearMessages, loadLanguage, loadMessages, newId, saveLanguage, saveMessages } from '@/lib/chiedi/storage'
import {
  citationsOf,
  isAssistant,
  type AssistantMessage,
  type ChatMessage,
  type ChiediCitation,
  type ChiediResponse,
  type Language,
} from '@/lib/chiedi/types'
import { AnswerTurn } from './AnswerTurn'
import { Composer, type ComposerHandle } from './Composer'
import { SourcesMargin } from './SourcesMargin'

interface QABody {
  question: string
  language: Language
  company_profile?: CompanyProfile
}

/** Bookkeeping of one streamed answer, outside React state. */
interface StreamRun {
  id: string
  tokens: number
  settled: boolean
  citations: ChiediCitation[]
  error?: string
}

type ScrollTarget = { target: 'source' | 'marker' | 'turn'; messageId: string; index: number }

function prefersReducedMotion(): boolean {
  try {
    return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

function isVisible(el: Element | null): el is HTMLElement {
  return !!el && (el as HTMLElement).offsetParent !== null
}

function bringIntoView(el: HTMLElement, block: ScrollLogicalPosition, focus: boolean) {
  if (typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ block, behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  }
  if (focus) el.focus({ preventScroll: true })
}

export function ChiediPage() {
  const t = useTranslations('chiedi')
  const ctx = useTextContext()
  const errorText = useErrorText()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { toast } = useToast()
  const { profile, setProfile } = useCompanyProfile()

  const [demo] = useState(() => isDemoMode())
  // Before the first answer, the corpus date comes from /api/v1/stats.
  const [statsCorpus, setStatsCorpus] = useState<string | undefined>(undefined)
  useEffect(() => {
    if (demo) return
    let alive = true
    api
      .get<{ corpus_as_of?: string | null }>('/api/v1/stats')
      .then((stats) => {
        if (alive && stats?.corpus_as_of) setStatsCorpus(stats.corpus_as_of)
      })
      .catch(() => {
        /* the meta line simply stays empty */
      })
    return () => {
      alive = false
    }
  }, [demo])
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadMessages(t('errors.reloaded')))
  // The answer language follows the interface unless overridden here.
  const [override, setOverride] = useState<Language | null>(() => loadLanguage())
  const language: Language = override ?? languageOf(ctx.locale)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [active, setActive] = useState<{ messageId: string; index: number } | null>(null)
  const [marginMessageId, setMarginMessageId] = useState<string | null>(null)
  const [openSources, setOpenSources] = useState<Record<string, boolean>>({})
  const [pendingScroll, setPendingScroll] = useState<ScrollTarget | null>(null)

  const composerRef = useRef<ComposerHandle>(null)
  const busyRef = useRef(false)
  const runIdRef = useRef<string | null>(null)
  const currentRef = useRef<StreamRun | null>(null)

  // ─── Message updates ───────────────────────────────────────

  const patch = useCallback((id: string, fn: (m: AssistantMessage) => AssistantMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === id && m.role === 'assistant' ? fn(m) : m)))
  }, [])

  useEffect(() => {
    saveMessages(messages)
  }, [messages])

  // ─── Streaming (live backend) ──────────────────────────────
  // The callbacks are stable on purpose: useSSEStream captures them when it
  // builds startStream, so they read the current run through a ref.

  const onToken = useCallback(
    (content: string) => {
      const run = currentRef.current
      if (!run || run.settled) return
      run.tokens += 1
      patch(run.id, (m) => ({ ...m, status: 'streaming', content: m.content + content }))
    },
    [patch],
  )

  const onCitation = useCallback(
    (ev: CitationEvent) => {
      const run = currentRef.current
      if (!run || run.settled) return
      run.citations = [...run.citations, sseCitationToChiedi(ev)]
      const citations = run.citations
      patch(run.id, (m) => ({ ...m, streamCitations: citations }))
    },
    [patch],
  )

  const onPhaseChange = useCallback(
    (phase: string) => {
      const run = currentRef.current
      if (!run || run.settled) return
      patch(run.id, (m) => ({ ...m, status: 'streaming', phase }))
    },
    [patch],
  )

  const onError = useCallback((message: string) => {
    const run = currentRef.current
    if (run) run.error = message
  }, [])

  const onDone = useCallback(
    (stats: DoneStats) => {
      const run = currentRef.current
      if (!run || run.settled) return
      run.settled = true
      const citations = run.citations
      patch(run.id, (m) => {
        if (!m.content.trim()) {
          return { ...m, status: 'error', error: t('errors.empty'), phase: undefined }
        }
        const data: ChiediResponse = {
          answer: m.content,
          citations,
          confidence_score: stats.confidence_score,
          requires_expert_review: stats.requires_review,
          related_frameworks: [],
          caveats: [],
          cove_applied: stats.cove_applied,
        }
        return { ...m, status: 'done', data, phase: undefined, streamCitations: undefined }
      })
    },
    [patch, t],
  )

  const { startStream, stopStream } = useSSEStream({
    onToken,
    onCitation,
    onPhaseChange,
    onError,
    onDone,
    autoReconnect: false,
  })

  // ─── Asking ────────────────────────────────────────────────

  const runPost = useCallback(
    async (id: string, body: QABody) => {
      try {
        const res = await api.post<ApiResponse<ChiediResponse>>('/api/v1/qa', body)
        const data = res?.data
        if (!data || typeof data.answer !== 'string') {
          throw new Error(t('errors.invalid'))
        }
        const corpusAsOf = corpusDateFrom(res.metadata, data)
        patch(id, (m) => ({
          ...m,
          status: 'done',
          content: data.answer,
          data: { ...data, citations: Array.isArray(data.citations) ? data.citations : [] },
          corpusAsOf,
          phase: undefined,
          streamCitations: undefined,
        }))
      } catch (err) {
        const message = errorText(err, 'errors.network')
        patch(id, (m) => ({ ...m, status: 'error', error: message, phase: undefined }))
      }
    },
    [errorText, patch, t],
  )

  const runStream = useCallback(
    async (id: string, body: QABody) => {
      const run: StreamRun = { id, tokens: 0, settled: false, citations: [] }
      currentRef.current = run
      patch(id, (m) => ({ ...m, status: 'loading', content: '', streamCitations: [] }))
      await startStream(`${api.getBaseUrl()}/api/v1/qa/stream`, body, getAccessToken() ?? '')
      if (currentRef.current !== run || run.settled) return
      run.settled = true
      if (run.tokens === 0) {
        // Nothing arrived: ask the same question without streaming.
        if (run.error) console.warn('qa/stream failed before the first token, using /api/v1/qa:', run.error)
        await runPost(id, body)
        return
      }
      console.warn('qa/stream ended before the done event:', run.error ?? 'connection closed')
      patch(id, (m) => ({ ...m, status: 'error', error: t('errors.interrupted'), phase: undefined }))
    },
    [patch, runPost, startStream, t],
  )

  const run = useCallback(
    async (id: string, question: string, lang: Language) => {
      busyRef.current = true
      runIdRef.current = id
      setBusy(true)
      const body: QABody = {
        question,
        language: lang,
        company_profile: profile.name.trim() ? profile : undefined,
      }
      try {
        if (demo || !getAccessToken()) await runPost(id, body)
        else await runStream(id, body)
      } finally {
        if (runIdRef.current === id) {
          runIdRef.current = null
          currentRef.current = null
          busyRef.current = false
          setBusy(false)
        }
      }
    },
    [demo, profile, runPost, runStream],
  )

  const send = useCallback(
    (question: string) => {
      const q = question.trim()
      if (!q || busyRef.current) return
      const now = new Date().toISOString()
      const userId = newId('u')
      const assistantId = newId('a')
      setMessages((prev) => [
        ...prev,
        { id: userId, role: 'user', content: q, timestamp: now },
        { id: assistantId, role: 'assistant', status: 'loading', question: q, language, content: '', timestamp: now },
      ])
      setDraft('')
      setActive(null)
      setMarginMessageId(assistantId)
      setPendingScroll({ target: 'turn', messageId: userId, index: 0 })
      void run(assistantId, q, language)
    },
    [language, run],
  )

  const retry = useCallback(
    (m: AssistantMessage) => {
      if (busyRef.current) return
      patch(m.id, (x) => ({ ...x, status: 'loading', error: undefined, content: '', data: undefined, phase: undefined, streamCitations: undefined }))
      setMarginMessageId(m.id)
      void run(m.id, m.question, m.language)
    },
    [patch, run],
  )

  const newConversation = useCallback(() => {
    stopStream()
    currentRef.current = null
    runIdRef.current = null
    busyRef.current = false
    setBusy(false)
    setMessages([])
    clearMessages()
    setActive(null)
    setMarginMessageId(null)
    setOpenSources({})
    setDraft('')
    composerRef.current?.focus()
  }, [stopStream])

  // The home page links here with ?q=: the question is sent once.
  const autoSentRef = useRef<string | null>(null)
  useEffect(() => {
    const q = searchParams.get('q')?.trim()
    if (!q || autoSentRef.current === q) return
    autoSentRef.current = q
    send(q)
    router.replace('/app/chiedi', { scroll: false })
  }, [searchParams, send, router])

  const setLanguage = (lang: Language) => {
    setOverride(lang)
    saveLanguage(lang)
  }

  // ─── Sources and markers ───────────────────────────────────

  const goToSource = useCallback((messageId: string, index: number) => {
    setActive({ messageId, index })
    setMarginMessageId(messageId)
    setOpenSources((s) => (s[messageId] ? s : { ...s, [messageId]: true }))
    setPendingScroll({ target: 'source', messageId, index })
  }, [])

  const goToMarker = useCallback((messageId: string, index: number) => {
    setActive({ messageId, index })
    setMarginMessageId(messageId)
    setPendingScroll({ target: 'marker', messageId, index })
  }, [])

  useEffect(() => {
    if (!pendingScroll || typeof document === 'undefined') return
    const { target, messageId, index } = pendingScroll
    setPendingScroll(null)
    if (target === 'turn') {
      const el = document.getElementById(`turn-${messageId}`)
      if (el) bringIntoView(el, 'start', false)
      return
    }
    if (target === 'marker') {
      const el = document.querySelector(`[data-marker="${messageId}-${index}"]`)
      if (isVisible(el)) bringIntoView(el, 'center', true)
      return
    }
    for (const id of [`source-${messageId}-${index}`, `source-m-${messageId}-${index}`]) {
      const el = document.getElementById(id)
      if (isVisible(el)) {
        bringIntoView(el, 'nearest', true)
        return
      }
    }
  }, [pendingScroll])

  const prefill = useCallback((question: string) => {
    setDraft(question)
    composerRef.current?.focus()
  }, [])

  const copy = useCallback(
    async (text: string) => {
      const ok = await copyToClipboard(text)
      toast(
        ok
          ? { kind: 'ok', title: t('copy.ok'), description: t('copy.okDescription') }
          : { kind: 'bad', title: t('copy.failed'), description: t('copy.failedDescription') },
      )
    },
    [t, toast],
  )

  // ─── Derived view state ────────────────────────────────────

  const answers = useMemo(() => messages.filter(isAssistant), [messages])
  const marginMessage = useMemo(
    () => (marginMessageId ? answers.find((m) => m.id === marginMessageId) : undefined) ?? answers[answers.length - 1],
    [answers, marginMessageId],
  )
  const marginSources = useMemo(
    () => (marginMessage ? citationsToSources(citationsOf(marginMessage), marginMessage.id, ctx) : []),
    [ctx, marginMessage],
  )
  const corpusAsOf = useMemo(() => {
    for (let i = answers.length - 1; i >= 0; i--) if (answers[i].corpusAsOf) return answers[i].corpusAsOf
    return undefined
  }, [answers])
  const corpusLabel = formatCorpusDate(corpusAsOf ?? statsCorpus, ctx.locale)
  const last = answers[answers.length - 1]
  const liveText = !last
    ? ''
    : last.status === 'loading'
      ? phaseLabel(undefined, ctx.t)
      : last.status === 'streaming'
        ? phaseLabel(last.phase ?? 'draft', ctx.t)
        : last.status === 'error'
          ? t('live.error')
          : t('live.ready')

  const profileForm = (idPrefix: string) => (
    <CompanyProfileForm idPrefix={idPrefix} value={profile} onChange={setProfile} />
  )

  return (
    <div>
      <PageHeader
        title={t('title')}
        description={t('description')}
        meta={corpusLabel ? t(demo ? 'corpusMetaDemo' : 'corpusMeta', { date: corpusLabel }) : undefined}
        actions={
          <>
            <div className="w-32">
              <label htmlFor="chiedi-language" className="sr-only">
                {t('answerLanguage')}
              </label>
              <Select
                id="chiedi-language"
                value={language}
                onChange={(e) => setLanguage(e.target.value === 'en' ? 'en' : 'it')}
                title={t('answerLanguage')}
                className="text-small"
              >
                <option value="it">{t('languages.it')}</option>
                <option value="en">{t('languages.en')}</option>
              </Select>
            </div>
            <Button variant="secondary" onClick={newConversation} disabled={messages.length === 0 && !draft}>
              {t('newConversation')}
            </Button>
          </>
        }
      />

      <div className="sr-only" role="status" aria-live="polite">
        {liveText}
      </div>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 max-w-prose">
          {messages.length === 0 ? (
            <EmptyState
              title={t('empty.title')}
              description={t('empty.description')}
              action={
                <ul className="flex flex-wrap justify-center gap-2" aria-label={t('examples')}>
                  {itemKeys(t.raw('suggestions')).map((k) => {
                    const s = t(`suggestions.${k}`)
                    return (
                      <li key={k}>
                        <button
                          type="button"
                          onClick={() => prefill(s)}
                          className="rounded-md border border-rule bg-surface px-3 py-1.5 text-left text-small text-ink-2 hover:border-rule-2 hover:text-ink"
                        >
                          {s}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              }
            />
          ) : (
            <ol className="divide-y divide-rule" aria-label={t('conversation')}>
              {messages.map((m) => (
                <li key={m.id} id={`turn-${m.id}`} className="py-6 first:pt-0">
                  {m.role === 'user' ? (
                    <div>
                      <p className="text-small text-ink-3">{t('questionLabel')}</p>
                      <p className="mt-1 whitespace-pre-wrap text-read font-medium text-ink">{m.content}</p>
                    </div>
                  ) : (
                    <AnswerTurn
                      message={m}
                      demo={demo}
                      activeIndex={active?.messageId === m.id ? active.index : null}
                      sourcesOpen={!!openSources[m.id]}
                      onToggleSources={() => setOpenSources((s) => ({ ...s, [m.id]: !s[m.id] }))}
                      onMarkerClick={(index) => goToSource(m.id, index)}
                      onSourceSelect={(index) => goToMarker(m.id, index)}
                      onFollowUp={prefill}
                      onRetry={() => retry(m)}
                      onCopy={copy}
                    />
                  )}
                </li>
              ))}
            </ol>
          )}

          <div className="mt-6 lg:hidden">{profileForm('cp-top')}</div>

          <div className="mt-6">
            <Composer ref={composerRef} value={draft} onChange={setDraft} onSubmit={send} busy={busy} />
          </div>
        </div>

        <SourcesMargin
          message={marginMessage}
          sources={marginSources}
          activeIndex={marginMessage && active?.messageId === marginMessage.id ? active.index : null}
          totalAnswers={answers.length}
          onSelect={(index) => marginMessage && goToMarker(marginMessage.id, index)}
        >
          {profileForm('cp')}
        </SourcesMargin>
      </div>
    </div>
  )
}
