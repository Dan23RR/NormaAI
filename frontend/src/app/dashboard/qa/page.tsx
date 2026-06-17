'use client'

import { useState, useRef, useEffect } from 'react'
import { api } from '@/lib/api'
import type { QAResponse, ApiResponse, CompanyProfile } from '@/lib/types'
import CompanyProfileForm, { useCompanyProfile } from '@/components/CompanyProfileForm'
import { Send, AlertTriangle, BookOpen, Loader2 } from 'lucide-react'
import { getConfidenceLabel } from '@/lib/confidence-labels'

const QA_LANGUAGE_KEY = 'normaai_qa_language'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  data?: QAResponse
  error?: string
  timestamp: Date
}

const QA_STORAGE_KEY = 'normaai_qa_messages'

function loadSavedMessages(): ChatMessage[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = sessionStorage.getItem(QA_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return parsed.map((m: Record<string, unknown>) => ({ ...m, timestamp: new Date(m.timestamp as string) }))
  } catch { return [] }
}

export default function QAPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(loadSavedMessages)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [language, setLanguageState] = useState(() => {
    if (typeof window === 'undefined') return 'it'
    return localStorage.getItem(QA_LANGUAGE_KEY) || 'it'
  })
  const setLanguage = (lang: string) => {
    setLanguageState(lang)
    localStorage.setItem(QA_LANGUAGE_KEY, lang)
  }
  const { profile, setProfile } = useCompanyProfile()
  const [streaming, setStreaming] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const streamIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Cleanup streaming interval on unmount
  useEffect(() => {
    return () => {
      if (streamIntervalRef.current) clearInterval(streamIntervalRef.current)
    }
  }, [])

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Persist messages to sessionStorage (skip partial streaming messages)
  useEffect(() => {
    if (messages.length > 0) {
      try {
        const persistable = messages.filter(
          m => m.role === 'user' || m.data || m.error
        )
        if (persistable.length > 0) {
          sessionStorage.setItem(QA_STORAGE_KEY, JSON.stringify(persistable))
        }
      } catch { /* ignore */ }
    }
  }, [messages])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const question = input.trim()
    if (!question || loading || streaming) return

    setInput('')
    setLoading(true)

    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: question, timestamp: new Date() }])

    try {
      const hasProfile = profile.name.length > 0
      const res = await api.post<ApiResponse<QAResponse>>('/api/v1/qa', {
        question,
        language,
        company_profile: hasProfile ? profile : undefined,
      })

      const fullAnswer = res.data.answer || ''

      // Add empty assistant message to start streaming into
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '',
        timestamp: new Date(),
      }])
      setLoading(false)
      setStreaming(true)

      // Stream the answer character by character
      let charIndex = 0
      streamIntervalRef.current = setInterval(() => {
        charIndex += 2 // 2 chars at a time for natural speed
        if (charIndex >= fullAnswer.length) {
          if (streamIntervalRef.current) clearInterval(streamIntervalRef.current)
          streamIntervalRef.current = null
          // Replace with full message including metadata (citations, confidence, etc.)
          setMessages(prev => {
            const updated = [...prev]
            updated[updated.length - 1] = {
              role: 'assistant',
              content: fullAnswer,
              data: res.data,
              timestamp: new Date(),
            }
            return updated
          })
          setStreaming(false)
          return
        }
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            content: fullAnswer.slice(0, charIndex),
          }
          return updated
        })
      }, 15)
    } catch (err: unknown) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '',
        error: err instanceof Error ? err.message : 'Request failed',
        timestamp: new Date(),
      }])
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col lg:flex-row gap-4 h-[calc(100vh-8rem)]">
      {/* Chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto space-y-4 pb-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
              <BookOpen size={40} className="mb-3 text-slate-600" />
              <p className="text-lg font-medium text-slate-400">Ask about EU Regulations</p>
              <p className="text-sm mt-1">Get AI-powered answers with precise article citations</p>
              <p className="text-[10px] text-slate-600 mt-4 max-w-sm text-center leading-relaxed">
                Le risposte sono generate da un sistema di intelligenza artificiale (AI Act Art. 50, Reg. UE 2024/1689).
                Verificare sempre con fonti ufficiali e consulenti qualificati.
              </p>
              <div className="flex flex-wrap gap-2 mt-6 max-w-lg justify-center">
                {[
                  'Does my company need to file a CSRD report?',
                  'What are the key obligations under DORA?',
                  'NIS2 incident reporting requirements',
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => setInput(q)}
                    className="px-3 py-1.5 text-xs bg-surface2 border border-white/[0.06] rounded-lg text-slate-400 hover:text-white hover:border-accent/30 transition"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-2xl rounded-xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-accent/10 border border-accent/20 text-white'
                  : 'bg-surface border border-white/[0.06]'
              }`}>
                {msg.error ? (
                  <div className="flex items-center gap-2 text-red-400 text-sm">
                    <AlertTriangle size={16} />
                    {msg.error}
                  </div>
                ) : (
                  <>
                    <p className="text-sm leading-relaxed whitespace-pre-wrap">
                      {msg.content}
                      {i === messages.length - 1 && !msg.data && !msg.error && msg.content && (
                        <span className="inline-block w-0.5 h-4 bg-accent animate-pulse ml-0.5 -mb-0.5 align-text-bottom" />
                      )}
                    </p>

                    {msg.data && (
                      <div className="mt-3 space-y-2">
                        {/* Confidence */}
                        <ConfidenceBadge score={msg.data.confidence_score} review={msg.data.requires_expert_review} />

                        {/* Citations */}
                        {msg.data.citations?.length > 0 && (
                          <div className="space-y-1">
                            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Citations</div>
                            {msg.data.citations.map((c, j) => (
                              <div key={j} className="text-xs text-slate-400 bg-surface2 rounded px-2 py-1.5">
                                <span className="text-accent font-medium">[{c.framework}, {c.reference}]</span>{' '}
                                {c.quote_snippet}
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Related frameworks - clickable to drill down */}
                        {msg.data.related_frameworks?.length > 0 && (
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-[10px] uppercase text-slate-600">Related:</span>
                            {msg.data.related_frameworks.map(fw => (
                              <button
                                key={fw}
                                type="button"
                                onClick={() => {
                                  const followUp = `What are the key requirements under ${fw}?`
                                  setInput(followUp)
                                }}
                                className="text-[10px] px-1.5 py-0.5 bg-accent/10 text-accent rounded cursor-pointer hover:bg-accent/20 transition"
                                title={`Ask about ${fw}`}
                              >
                                {fw} →
                              </button>
                            ))}
                          </div>
                        )}

                        {/* Caveats */}
                        {msg.data.caveats?.length > 0 && (
                          <div className="mt-2 space-y-1">
                            {msg.data.caveats.map((caveat, j) => (
                              <div key={j} className="text-xs text-yellow-400/80 bg-yellow-400/5 rounded px-2 py-1.5 flex items-start gap-1.5">
                                <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                                {caveat}
                              </div>
                            ))}
                          </div>
                        )}

                        {/* AI disclosure */}
                        <p className="text-[9px] text-slate-600 mt-2 italic">
                          Risposta generata da AI - verificare con fonti ufficiali prima di decisioni vincolanti.
                        </p>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="bg-surface border border-white/[0.06] rounded-xl px-4 py-3 flex items-center gap-2 text-slate-400 text-sm">
                <Loader2 size={16} className="animate-spin" />
                Analyzing regulations...
              </div>
            </div>
          )}

          <div ref={scrollRef} />
        </div>

        {/* Language warning banner */}
        {language !== 'it' && (
          <div className="px-3 py-2 bg-yellow-400/5 border border-yellow-400/20 rounded-lg text-yellow-400 text-xs flex items-center gap-2">
            <AlertTriangle size={14} className="shrink-0" />
            <span>Modalità demo: le risposte sono disponibili solo in italiano. In produzione NormaAI risponde in {language === 'en' ? 'English' : language.toUpperCase()}.</span>
          </div>
        )}

        {/* Input */}
        <form onSubmit={handleSubmit} className="flex gap-2" aria-label="Invia domanda">
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="hidden sm:block px-3 py-2.5 bg-surface border border-white/[0.06] rounded-lg text-sm text-slate-300 focus:outline-none"
            aria-label="Lingua risposta"
          >
            <option value="it">IT</option>
            <option value="en">EN</option>
          </select>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about EU regulations..."
            className="flex-1 min-w-0 px-4 py-2.5 bg-surface border border-white/[0.06] rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-accent/40 transition"
            disabled={loading || streaming}
            aria-label="La tua domanda"
          />
          <button
            type="submit"
            disabled={loading || streaming || !input.trim()}
            className="px-4 py-2.5 rounded-lg bg-gradient-to-r from-accent to-accent2 text-white hover:opacity-90 transition disabled:opacity-30 shrink-0"
            aria-label="Invia"
          >
            <Send size={18} />
          </button>
        </form>
      </div>

      {/* Sidebar: Company Profile */}
      <div className="w-full lg:w-80 shrink-0 order-first lg:order-last">
        <CompanyProfileForm value={profile} onChange={setProfile} />
      </div>
    </div>
  )
}

function ConfidenceBadge({ score, review }: { score: number; review: boolean }) {
  const conf = getConfidenceLabel(score)

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${conf.color} ${conf.bg} ${conf.border}`}>
          {conf.label}
        </span>
        <span className="text-[10px] px-2 py-0.5 rounded border border-amber-400/20 bg-amber-400/10 text-amber-400 flex items-center gap-1">
          <AlertTriangle size={10} /> {review ? 'Revisione esperto consigliata' : 'Verifica sempre raccomandata'}
        </span>
      </div>
      <p className="text-[9px] text-slate-600">{conf.sublabel}</p>
    </div>
  )
}
