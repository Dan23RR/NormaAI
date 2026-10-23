import type { AssistantMessage, ChatMessage, ChiediResponse, Language, UserMessage } from './types'

export const QA_STORAGE_KEY = 'normaai_qa_messages'
export const QA_LANGUAGE_KEY = 'normaai_qa_language'

export function newId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function isoOf(value: unknown): string {
  if (typeof value === 'string' && !Number.isNaN(new Date(value).getTime())) return value
  return new Date().toISOString()
}

/**
 * The conversation kept for this tab. Entries written by the previous
 * version of the page (no id, `timestamp` as a Date, partial answers) are
 * normalised; an answer that never completed is dropped, and a question
 * left without an answer gets an error turn so it can be retried.
 */
export function loadMessages(): ChatMessage[] {
  if (typeof window === 'undefined') return []
  let parsed: unknown
  try {
    const raw = sessionStorage.getItem(QA_STORAGE_KEY)
    if (!raw) return []
    parsed = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(parsed)) return []

  const out: ChatMessage[] = []
  let lastQuestion = ''
  for (const item of parsed as Array<Record<string, unknown>>) {
    if (!item || typeof item !== 'object') continue
    if (item.role === 'user' && typeof item.content === 'string') {
      const msg: UserMessage = {
        id: typeof item.id === 'string' ? item.id : newId('u'),
        role: 'user',
        content: item.content,
        timestamp: isoOf(item.timestamp),
      }
      lastQuestion = item.content
      out.push(msg)
      continue
    }
    if (item.role !== 'assistant') continue
    const base = {
      id: typeof item.id === 'string' ? item.id : newId('a'),
      role: 'assistant' as const,
      question: typeof item.question === 'string' ? item.question : lastQuestion,
      language: (item.language === 'en' ? 'en' : 'it') as Language,
      timestamp: isoOf(item.timestamp),
      corpusAsOf: typeof item.corpusAsOf === 'string' ? item.corpusAsOf : undefined,
    }
    if (item.data && typeof item.data === 'object') {
      const data = item.data as ChiediResponse
      const msg: AssistantMessage = {
        ...base,
        status: 'done',
        content: typeof item.content === 'string' && item.content ? item.content : (data.answer ?? ''),
        data: { ...data, citations: Array.isArray(data.citations) ? data.citations : [] },
      }
      out.push(msg)
    } else if (typeof item.error === 'string' && item.error) {
      out.push({ ...base, status: 'error', content: '', error: item.error })
    }
  }

  const last = out[out.length - 1]
  if (last && last.role === 'user') {
    out.push({
      id: newId('a'),
      role: 'assistant',
      status: 'error',
      question: last.content,
      language: 'it',
      content: '',
      error: 'La risposta non è arrivata prima che la pagina fosse ricaricata. Riprova.',
      timestamp: new Date().toISOString(),
    })
  }
  return out
}

/** Persist the conversation without the partial states of a running answer. */
export function saveMessages(messages: ChatMessage[]): void {
  if (typeof window === 'undefined') return
  const persistable: ChatMessage[] = []
  for (const m of messages) {
    if (m.role === 'user') {
      persistable.push(m)
      continue
    }
    if (m.status !== 'done' && m.status !== 'error') continue
    const { streamCitations: _stream, phase: _phase, ...rest } = m
    void _stream
    void _phase
    persistable.push(rest)
  }
  try {
    if (persistable.length === 0) sessionStorage.removeItem(QA_STORAGE_KEY)
    else sessionStorage.setItem(QA_STORAGE_KEY, JSON.stringify(persistable))
  } catch {
    /* storage full or blocked: the conversation stays in memory */
  }
}

export function clearMessages(): void {
  if (typeof window === 'undefined') return
  try {
    sessionStorage.removeItem(QA_STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

export function loadLanguage(): Language {
  if (typeof window === 'undefined') return 'it'
  try {
    return localStorage.getItem(QA_LANGUAGE_KEY) === 'en' ? 'en' : 'it'
  } catch {
    return 'it'
  }
}

export function saveLanguage(lang: Language): void {
  try {
    localStorage.setItem(QA_LANGUAGE_KEY, lang)
  } catch {
    /* preference stays for this page only */
  }
}
