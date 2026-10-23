'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { api, NETWORK_ERROR } from '@/lib/api'
import { getAccessToken, isDemoMode } from '@/lib/auth'
import type { ApiResponse, CompanyProfile } from '@/lib/types'
import { useSSEStream, type CitationEvent, type DoneStats } from '@/hooks/useSSEStream'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Field'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageHeader } from '@/components/ui/PageHeader'
import { useToast } from '@/components/ui/Toast'
import CompanyProfileForm, { useCompanyProfile } from '@/components/CompanyProfileForm'
import { copyToClipboard } from '@/lib/chiedi/copy'
import { corpusDateFrom, formatItalianDate } from '@/lib/chiedi/dates'
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

const SUGGESTIONS = [
  'La nostra società con 600 dipendenti rientra ancora nella CSRD dopo l’Omnibus?',
  'Un chatbot sul sito aziendale deve dichiarare di essere un’IA?',
  'Quali incidenti vanno notificati entro 24 ore secondo la NIS2?',
]

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
  const router = useRouter()
  const searchParams = useSearchParams()
  const { toast } = useToast()
  const { profile, setProfile } = useCompanyProfile()

  const [demo] = useState(() => isDemoMode())
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadMessages())
  const [language, setLanguageState] = useState<Language>(() => loadLanguage())
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
          return { ...m, status: 'error', error: 'Il server ha restituito una risposta vuota. Riprova.', phase: undefined }
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
    [patch],
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
          throw new Error('Il server ha restituito una risposta non valida. Riprova.')
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
        const message = err instanceof Error && err.message ? err.message : NETWORK_ERROR
        patch(id, (m) => ({ ...m, status: 'error', error: message, phase: undefined }))
      }
    },
    [patch],
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
      patch(id, (m) => ({ ...m, status: 'error', error: 'La risposta si è interrotta prima della fine. Riprova.', phase: undefined }))
    },
    [patch, runPost, startStream],
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
    setLanguageState(lang)
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
          ? { kind: 'ok', title: 'Copiato', description: 'Risposta e fonti sono negli appunti.' }
          : { kind: 'bad', title: 'Copia non riuscita', description: 'Seleziona il testo e copialo a mano.' },
      )
    },
    [toast],
  )

  // ─── Derived view state ────────────────────────────────────

  const answers = useMemo(() => messages.filter(isAssistant), [messages])
  const marginMessage = useMemo(
    () => (marginMessageId ? answers.find((m) => m.id === marginMessageId) : undefined) ?? answers[answers.length - 1],
    [answers, marginMessageId],
  )
  const marginSources = useMemo(
    () => (marginMessage ? citationsToSources(citationsOf(marginMessage), marginMessage.id) : []),
    [marginMessage],
  )
  const corpusAsOf = useMemo(() => {
    for (let i = answers.length - 1; i >= 0; i--) if (answers[i].corpusAsOf) return answers[i].corpusAsOf
    return undefined
  }, [answers])
  const corpusLabel = formatItalianDate(corpusAsOf)
  const last = answers[answers.length - 1]
  const liveText = !last
    ? ''
    : last.status === 'loading'
      ? phaseLabel(undefined)
      : last.status === 'streaming'
        ? phaseLabel(last.phase ?? 'draft')
        : last.status === 'error'
          ? 'La risposta non è arrivata'
          : 'Risposta pronta'

  const profileForm = (idPrefix: string) => (
    <CompanyProfileForm idPrefix={idPrefix} value={profile} onChange={setProfile} />
  )

  return (
    <div>
      <PageHeader
        title="Chiedi"
        description="Una domanda sul diritto dell'Unione, una risposta con l'atto, l'articolo e il passaggio di legge."
        meta={corpusLabel ? `Corpus al ${corpusLabel}${demo ? ' (dati di esempio)' : ''}` : undefined}
        actions={
          <>
            <div className="w-32">
              <label htmlFor="chiedi-language" className="sr-only">
                Lingua della risposta
              </label>
              <Select
                id="chiedi-language"
                value={language}
                onChange={(e) => setLanguage(e.target.value === 'en' ? 'en' : 'it')}
                title="Lingua della risposta"
                className="text-small"
              >
                <option value="it">Italiano</option>
                <option value="en">English</option>
              </Select>
            </div>
            <Button variant="secondary" onClick={newConversation} disabled={messages.length === 0 && !draft}>
              Nuova conversazione
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
              title="Cosa vuoi sapere?"
              description="Scrivi la domanda con il contesto che serve: settore, dimensione, Paese. La risposta cita l'atto, l'articolo e il passaggio di legge, con il link al testo ufficiale. Quando il testo non basta, NormaAI lo dice."
              action={
                <ul className="flex flex-wrap justify-center gap-2" aria-label="Esempi di domande">
                  {SUGGESTIONS.map((s) => (
                    <li key={s}>
                      <button
                        type="button"
                        onClick={() => prefill(s)}
                        className="rounded-md border border-rule bg-surface px-3 py-1.5 text-left text-small text-ink-2 hover:border-rule-2 hover:text-ink"
                      >
                        {s}
                      </button>
                    </li>
                  ))}
                </ul>
              }
            />
          ) : (
            <ol className="divide-y divide-rule" aria-label="Conversazione">
              {messages.map((m) => (
                <li key={m.id} id={`turn-${m.id}`} className="py-6 first:pt-0">
                  {m.role === 'user' ? (
                    <div>
                      <p className="text-small text-ink-3">Domanda</p>
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
