import { afterEach, describe, it, expect } from 'vitest'
import {
  DEMO_ACT_VERSIONS,
  DEMO_ALERTS,
  DEMO_ALERT_SUMMARY,
  DEMO_CLIENTS,
  DEMO_CORPUS_AS_OF,
  DEMO_PROCESSORS,
  DEMO_STATS,
  DEMO_USER,
  demoLanguage,
  getDemoAlerts,
  getMockGapAnalysis,
  getMockMonitorResponse,
  getMockQAResponse,
  mockDelay,
  qaScenarioOf,
} from '../mock-data'
import { QA_EN, SUGGESTED_QUESTIONS_EN } from '../demo/qa-en'
import { QA_IT, SUGGESTED_QUESTIONS_IT } from '../demo/qa-it'
import type { DemoQAScenario } from '../demo/types'

const BACKEND_FRAMEWORKS = ['CSRD', 'CSDDD', 'AI_ACT', 'DORA', 'NIS2', 'TAXONOMY', 'GDPR', 'CRA']
const LANGUAGES = ['it', 'en'] as const
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/** Em dash, en dash, ellipsis character, curly quotes: not used in the copy of the product. */
const FORBIDDEN_CHARACTERS = /[\u2013\u2014\u2026\u2018\u2019\u201c\u201d]/

const SME = { name: 'Alfa S.r.l.', sector: 'Meccanica', employee_count: 85, revenue_eur: 14_000_000 }
const LARGE = { name: 'Zeta S.p.A.', sector: 'Automotive', employee_count: 1650, revenue_eur: 520_000_000 }

function setLocaleCookie(language: 'it' | 'en') {
  document.cookie = `normaai.locale=${language}; path=/`
}

afterEach(() => {
  document.cookie = 'normaai.locale=; path=/; max-age=0'
})

describe('demo date', () => {
  it('is a fixed day, not in the future of the build', () => {
    expect(DEMO_CORPUS_AS_OF).toMatch(ISO_DATE)
    expect(new Date(DEMO_CORPUS_AS_OF).getTime()).toBeLessThanOrEqual(Date.now())
  })

  it('names the consolidated text of every amended act it quotes', () => {
    for (const [celex, asOf] of Object.entries(DEMO_ACT_VERSIONS)) {
      expect(celex).toMatch(/^3\d{4}[RL]\d{4}$/)
      expect(asOf).toMatch(ISO_DATE)
      expect(asOf <= DEMO_CORPUS_AS_OF).toBe(true)
    }
  })
})

describe('DEMO_STATS', () => {
  it('keeps the shape of GET /api/v1/stats', () => {
    expect(DEMO_STATS.environment).toBe('demo')
    expect(typeof DEMO_STATS.version).toBe('string')
    expect(typeof DEMO_STATS.qdrant_available).toBe('boolean')
    expect(typeof DEMO_STATS.llm_available).toBe('boolean')
    expect(typeof DEMO_STATS.metrics.total_requests).toBe('number')
    expect(typeof DEMO_STATS.metrics.error_count).toBe('number')
    expect(typeof DEMO_STATS.metrics.endpoints).toBe('object')
  })

  it('never reads as a live server', () => {
    expect(DEMO_STATS.status).not.toBe('healthy')
    expect(DEMO_STATS.qdrant_available).toBe(false)
    expect(DEMO_STATS.llm_available).toBe(false)
    expect(DEMO_STATS.llm_model).toBe('')
    expect(DEMO_STATS.metrics.total_requests).toBe(0)
    expect(Object.keys(DEMO_STATS.metrics.endpoints)).toHaveLength(0)
    // A fixed timestamp: the demo does not claim to have been read "now".
    expect(DEMO_STATS.timestamp.startsWith(DEMO_CORPUS_AS_OF)).toBe(true)
    expect(DEMO_PROCESSORS.engines).toHaveLength(0)
    expect(DEMO_PROCESSORS.docling.available).toBe(false)
  })
})

describe('DEMO_USER', () => {
  it('is an admin so the demo shows every surface', () => {
    expect(DEMO_USER.role).toBe('admin')
    expect(DEMO_USER.email).toContain('@')
  })

  it('is an invented person of a firm labelled as a demo', () => {
    // .example is reserved (RFC 2606): the address cannot belong to anybody.
    expect(DEMO_USER.email.endsWith('.example')).toBe(true)
    expect(DEMO_USER.organization_name.toLowerCase()).toContain('demo')
    expect(DEMO_USER.name).not.toMatch(/demo user/i)
  })
})

describe('DEMO_CLIENTS', () => {
  it('has unique ids and the fields the clients API returns', () => {
    const ids = DEMO_CLIENTS.map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const client of DEMO_CLIENTS) {
      expect(client.name.length).toBeGreaterThan(0)
      expect(typeof client.employee_count).toBe('number')
      expect(typeof client.revenue_eur).toBe('number')
      expect(Array.isArray(client.jurisdictions)).toBe(true)
      expect(Array.isArray(client.applicable_frameworks)).toBe(true)
      expect(new Date(client.created_at).getTime()).not.toBeNaN()
      expect(new Date(client.updated_at).getTime()).not.toBeNaN()
    }
  })

  it('uses the framework keys the backend accepts', () => {
    for (const client of DEMO_CLIENTS) {
      for (const fw of client.applicable_frameworks) {
        expect(BACKEND_FRAMEWORKS).toContain(fw)
      }
    }
  })

  it('is the portfolio of an Italian consultant: SMEs, at most one large company', () => {
    const smes = DEMO_CLIENTS.filter((c) => c.employee_count >= 15 && c.employee_count <= 250)
    expect(smes.length).toBeGreaterThanOrEqual(4)
    expect(smes.length).toBeLessThanOrEqual(6)
    expect(DEMO_CLIENTS.length - smes.length).toBeLessThanOrEqual(1)
    for (const client of DEMO_CLIENTS) {
      expect(client.jurisdictions).toContain('IT')
      expect(client.name).toMatch(/S\.r\.l\.|S\.p\.A\./)
    }
    for (const sme of smes) {
      // A medium-sized enterprise has a turnover of at most EUR 50 million.
      expect(sme.revenue_eur).toBeLessThanOrEqual(50_000_000)
      expect(sme.revenue_eur).toBeGreaterThan(1_000_000)
    }
  })

  it('follows only frameworks that can apply to a company of that size', () => {
    for (const client of DEMO_CLIENTS) {
      const csrd = client.employee_count > 1000 && client.revenue_eur > 450_000_000
      const csddd = client.employee_count > 5000 && client.revenue_eur > 1_500_000_000
      const smallEnterprise = client.employee_count < 50 && client.revenue_eur <= 10_000_000
      expect(client.applicable_frameworks.includes('CSRD'), client.name).toBe(csrd)
      expect(client.applicable_frameworks.includes('TAXONOMY'), client.name).toBe(csrd)
      expect(client.applicable_frameworks.includes('CSDDD'), client.name).toBe(csddd)
      if (smallEnterprise) expect(client.applicable_frameworks, client.name).not.toContain('NIS2')
      expect(client.applicable_frameworks, client.name).not.toContain('DORA')
    }
  })

  it('was created and updated before the demo date', () => {
    for (const client of DEMO_CLIENTS) {
      expect(client.created_at <= client.updated_at).toBe(true)
      expect(client.updated_at.slice(0, 10) <= DEMO_CORPUS_AS_OF).toBe(true)
    }
  })
})

describe('DEMO_ALERTS', () => {
  it('has fixed dates: none is created "now" and none was born with a deadline already passed', () => {
    for (const alert of DEMO_ALERTS) {
      expect(alert.created_at).toMatch(/^\d{4}-\d{2}-\d{2}T/)
      expect(alert.created_at.slice(0, 10) <= DEMO_CORPUS_AS_OF, alert.title).toBe(true)
      if (alert.deadline !== null) {
        expect(alert.deadline).toMatch(ISO_DATE)
        expect(alert.deadline > alert.created_at.slice(0, 10), alert.title).toBe(true)
      }
    }
  })

  it('refers to clients of the demo and to frameworks the interface knows', () => {
    const ids = new Set(DEMO_CLIENTS.map((c) => c.id))
    for (const alert of DEMO_ALERTS) {
      if (alert.client_id !== null) expect(ids.has(alert.client_id)).toBe(true)
      expect(BACKEND_FRAMEWORKS).toContain(alert.framework)
      expect(alert.source.length).toBeGreaterThan(0)
    }
  })

  it('has a summary that matches the list', () => {
    expect(DEMO_ALERT_SUMMARY.total).toBe(DEMO_ALERTS.length)
    expect(DEMO_ALERT_SUMMARY.unread).toBe(DEMO_ALERTS.filter((a) => !a.is_read).length)
    const bySeverity = Object.values(DEMO_ALERT_SUMMARY.by_severity).reduce((a, b) => a + b, 0)
    const byFramework = Object.values(DEMO_ALERT_SUMMARY.by_framework).reduce((a, b) => a + b, 0)
    expect(bySeverity).toBe(DEMO_ALERTS.length)
    expect(byFramework).toBe(DEMO_ALERTS.length)
  })

  it('is written in both languages, with the same structure', () => {
    const it_ = getDemoAlerts('it')
    const en = getDemoAlerts('en')
    expect(en).toHaveLength(it_.length)
    it_.forEach((alert, i) => {
      expect(en[i].id).toBe(alert.id)
      expect(en[i].deadline).toBe(alert.deadline)
      expect(en[i].title).not.toBe(alert.title)
      expect(en[i].actions_required).toHaveLength(alert.actions_required.length)
    })
  })

  it('follows the interface language when it is read', () => {
    expect(demoLanguage()).toBe('it')
    const italian = DEMO_ALERTS[0].title
    expect(italian).toBe(getDemoAlerts('it')[0].title)

    setLocaleCookie('en')
    expect(demoLanguage()).toBe('en')
    expect(DEMO_ALERTS[0].title).toBe(getDemoAlerts('en')[0].title)
    // A copy made by the page (mark as read) keeps every field.
    const copy = { ...DEMO_ALERTS[0], is_read: true }
    expect(copy.title).toBe(getDemoAlerts('en')[0].title)
    expect(copy.id).toBe(DEMO_ALERTS[0].id)
    expect(JSON.parse(JSON.stringify(DEMO_ALERTS))).toHaveLength(DEMO_ALERTS.length)
  })
})

describe('getMockGapAnalysis', () => {
  it('returns a consistent status summary for every framework, in both languages', () => {
    for (const language of LANGUAGES) {
      for (const fw of BACKEND_FRAMEWORKS) {
        for (const profile of [undefined, SME, LARGE]) {
          const result = getMockGapAnalysis(fw, profile, language)
          expect(result.framework).toBe(fw)
          expect(result.requirements.length).toBeGreaterThan(0)
          expect(result.overall_score).toBeGreaterThanOrEqual(0)
          expect(result.overall_score).toBeLessThanOrEqual(100)
          const counted = Object.values(result.status_summary).reduce((a, b) => a + b, 0)
          expect(counted).toBe(result.requirements.length)
          expect(result.top_recommendations.length).toBeGreaterThan(0)
          for (const req of result.requirements) {
            expect(req.description.length, `${fw} ${req.requirement_id}`).toBeGreaterThan(0)
            expect(req.article_reference.length, `${fw} ${req.requirement_id}`).toBeGreaterThan(0)
          }
        }
      }
    }
  })

  it('works with the framework alone, as the API client calls it today', () => {
    const result = getMockGapAnalysis('CSRD')
    expect(result.framework).toBe('CSRD')
    expect(result.requirements.length).toBeGreaterThan(0)
  })

  it('falls back to sample data for an unknown framework', () => {
    const result = getMockGapAnalysis('UNKNOWN')
    expect(result.requirements.length).toBeGreaterThan(0)
  })

  it('is deterministic: the same request gives the same analysis', () => {
    expect(getMockGapAnalysis('GDPR', SME, 'it')).toEqual(getMockGapAnalysis('GDPR', SME, 'it'))
  })

  it('writes Italian for Italian readers and English for English readers', () => {
    for (const fw of BACKEND_FRAMEWORKS) {
      const italian = getMockGapAnalysis(fw, SME, 'it')
      const english = getMockGapAnalysis(fw, SME, 'en')
      expect(english.requirements.map((r) => r.requirement_id)).toEqual(italian.requirements.map((r) => r.requirement_id))
      expect(english.requirements.map((r) => r.status)).toEqual(italian.requirements.map((r) => r.status))
      for (const req of italian.requirements) {
        expect(req.remediation_effort, `${fw} ${req.requirement_id}`).not.toMatch(/week/i)
        expect(req.description, `${fw} ${req.requirement_id}`).not.toMatch(/\b(assessment|disclosure|compliance|reporting)\b/i)
      }
      for (const req of english.requirements) {
        expect(req.remediation_effort, `${fw} ${req.requirement_id}`).not.toMatch(/settiman/i)
      }
      for (const rec of italian.top_recommendations) expect(rec).not.toMatch(/\b(the|and|with|for)\b/)
    }
  })

  it('does not ask a small company for what the law asks only of large ones', () => {
    for (const language of LANGUAGES) {
      const csrdSme = getMockGapAnalysis('CSRD', SME, language)
      expect(csrdSme.requirements[0].status).toBe('NOT_APPLICABLE')
      expect(csrdSme.requirements.some((r) => r.status === 'NON_COMPLIANT')).toBe(false)

      const csdddSme = getMockGapAnalysis('CSDDD', SME, language)
      expect(csdddSme.requirements[0].status).toBe('NOT_APPLICABLE')
      // 1,650 employees: above the CSRD thresholds, far below the CSDDD ones.
      expect(getMockGapAnalysis('CSDDD', LARGE, language).requirements[0].status).toBe('NOT_APPLICABLE')
      expect(getMockGapAnalysis('TAXONOMY', SME, language).requirements[0].status).toBe('NOT_APPLICABLE')
      expect(getMockGapAnalysis('DORA', SME, language).requirements[0].status).toBe('NOT_APPLICABLE')

      const csrdLarge = getMockGapAnalysis('CSRD', LARGE, language)
      expect(csrdLarge.requirements[0].status).toBe('COMPLIANT')
      expect(csrdLarge.requirements.length).toBeGreaterThan(csrdSme.requirements.length)
    }
    // A small enterprise (fewer than 50 persons, turnover up to EUR 10 million) is as a rule outside NIS2.
    const small = { name: 'Beta S.r.l.', sector: 'Software', employee_count: 32, revenue_eur: 3_800_000 }
    expect(getMockGapAnalysis('NIS2', small, 'it').requirements[0].status).toBe('NOT_APPLICABLE')
    expect(getMockGapAnalysis('NIS2', SME, 'it').requirements[0].status).toBe('IN_EVOLUTION')
  })

  it('says which companies a framework applies to when it does not know the company', () => {
    const csrd = getMockGapAnalysis('CSRD', undefined, 'it')
    expect(csrd.requirements[0].status).toBe('IN_EVOLUTION')
    expect(csrd.requirements[0].gap_description).toContain('1.000 dipendenti')
    expect(csrd.requirements[0].gap_description).toContain('450 milioni')
    const csddd = getMockGapAnalysis('CSDDD', undefined, 'en')
    expect(csddd.requirements[0].gap_description).toContain('5,000 employees')
    expect(csddd.requirements[0].gap_description).toContain('EUR 1.5 billion')
  })

  it('never brings back the climate transition plan that Omnibus I deleted from the CSDDD', () => {
    for (const language of LANGUAGES) {
      for (const profile of [undefined, SME, LARGE, { ...LARGE, employee_count: 9000, revenue_eur: 4_000_000_000 }]) {
        const text = JSON.stringify(getMockGapAnalysis('CSDDD', profile, language))
        expect(text).not.toMatch(/art\.? ?22\b/i)
        expect(text).not.toMatch(/transition plan|piano di transizione/i)
      }
    }
  })
})

describe('getMockMonitorResponse', () => {
  const CSRD_CHANGE = "L'Omnibus I (Direttiva (UE) 2026/470) ha alzato le soglie CSRD a più di 1.000 dipendenti e oltre 450 milioni di euro."

  it('returns an applicability and required actions', () => {
    const result = getMockMonitorResponse('Modifica delle soglie CSRD')
    expect(['YES', 'NO', 'CONDITIONAL']).toContain(result.applicability)
    expect(Array.isArray(result.required_actions)).toBe(true)
  })

  it('applies the CSRD thresholds cumulatively', () => {
    // 2,500 employees but EUR 200 million: one threshold is not enough.
    const oneThreshold = { name: 'Acme Srl', sector: 'Manufacturing', employee_count: 2500, revenue_eur: 200_000_000 }
    expect(getMockMonitorResponse(CSRD_CHANGE, oneThreshold, 'it').applicability).toBe('NO')
    expect(getMockMonitorResponse(CSRD_CHANGE, SME, 'it').applicability).toBe('NO')
    expect(getMockMonitorResponse(CSRD_CHANGE, LARGE, 'it').applicability).toBe('YES')
    // Exactly on a threshold is not "more than".
    const onThreshold = { ...LARGE, employee_count: 1000 }
    expect(getMockMonitorResponse(CSRD_CHANGE, onThreshold, 'it').applicability).toBe('NO')
  })

  it('does not decide without the size of the company', () => {
    expect(getMockMonitorResponse(CSRD_CHANGE).applicability).toBe('CONDITIONAL')
    expect(getMockMonitorResponse(CSRD_CHANGE, { name: 'X', sector: '', employee_count: 0, revenue_eur: 0 }).applicability).toBe('CONDITIONAL')
    expect(getMockMonitorResponse(undefined).applicability).toBe('CONDITIONAL')
  })

  it('gives every recognised act an answer in both languages, with a date that is a date', () => {
    const changes = [
      CSRD_CHANGE,
      'Nuove linee guida sulla CSDDD e il dovere di diligenza',
      'Criteri di vaglio tecnico della Tassonomia',
      "Orientamenti sull'AI Act per i sistemi ad alto rischio",
      'Parere sul GDPR e i dati personali',
      'Determinazione ACN sulla NIS2',
      'Norme tecniche DORA',
      'Atto di esecuzione del CRA sui prodotti con elementi digitali',
    ]
    for (const change of changes) {
      for (const profile of [undefined, SME, LARGE]) {
        const italian = getMockMonitorResponse(change, profile, 'it')
        const english = getMockMonitorResponse(change, profile, 'en')
        expect(english.applicability, change).toBe(italian.applicability)
        expect(english.deadline, change).toBe(italian.deadline)
        expect(english.applicability_reason, change).not.toBe(italian.applicability_reason)
        expect(italian.citations.length, change).toBeGreaterThan(0)
        expect(english.required_actions, change).toHaveLength(italian.required_actions.length)
        expect(italian.deadline === '' || ISO_DATE.test(italian.deadline), change).toBe(true)
        if (italian.deadline) expect(italian.deadline > DEMO_CORPUS_AS_OF, change).toBe(true)
        // The demo says what it did: it recognised the act, it did not read the change.
        expect(italian.impact_summary, change).toContain('Esempio della demo')
        expect(english.impact_summary, change).toContain('Demo example')
      }
    }
  })

  it('writes a correct sentence also when the profile has no name', () => {
    const anonymous = { sector: 'Servizi', employee_count: 85, revenue_eur: 14_000_000 }
    const outputs = [undefined, anonymous].flatMap((profile) =>
      LANGUAGES.flatMap((language) => [
        ...['csrd', 'csddd', 'tassonomia', 'ai act', 'gdpr', 'nis2', 'dora', 'cra'].map((t) => getMockMonitorResponse(t, profile, language)),
        ...BACKEND_FRAMEWORKS.map((fw) => getMockGapAnalysis(fw, profile, language)),
      ]),
    )
    const text = JSON.stringify(outputs)
    // The neutral subject is capitalised only where a sentence starts.
    expect(text).not.toMatch(/[a-zàèéìòù,:;] (L'impresa|The company)\b/)
    expect(text).not.toMatch(/"(l'impresa|the company)\b/)
    expect(text).not.toMatch(/undefined|NaN/)
  })

  it('says so when it does not recognise the act', () => {
    const result = getMockMonitorResponse('Una novità che non nomina alcun atto conosciuto', SME, 'it')
    expect(result.applicability).toBe('CONDITIONAL')
    expect(result.citations).toHaveLength(0)
    expect(result.applicability_reason).toContain('non ha riconosciuto')
    expect(JSON.stringify(result)).not.toMatch(/RAG|LLM/)
  })
})

describe('getMockQAResponse', () => {
  const scenarios = Object.keys(QA_IT) as DemoQAScenario[]

  it('has the same examples in Italian and in English, citation by citation', () => {
    expect(Object.keys(QA_EN).sort()).toEqual([...scenarios].sort())
    for (const key of scenarios) {
      const italian = QA_IT[key]
      const english = QA_EN[key]
      expect(english.citations, key).toHaveLength(italian.citations.length)
      italian.citations.forEach((c, i) => {
        expect(english.citations[i].celex, `${key} [${i + 1}]`).toBe(c.celex)
        expect(english.citations[i].verified, `${key} [${i + 1}]`).toBe(c.verified)
        expect(english.citations[i].framework, `${key} [${i + 1}]`).toBe(c.framework)
        expect(english.citations[i].url, `${key} [${i + 1}]`).toBe(c.url)
      })
      expect(english.confidence_score, key).toBe(italian.confidence_score)
      expect(english.caveats, key).toHaveLength(italian.caveats.length)
    }
  })

  it('cites every source it lists and lists every source it cites', () => {
    for (const [language, set] of [['it', QA_IT], ['en', QA_EN]] as const) {
      for (const key of scenarios) {
        const { answer, citations } = set[key]
        const markers = new Set(Array.from(answer.matchAll(/\[(\d+)\]/g), (m) => Number(m[1])))
        const expected = new Set(citations.map((_, i) => i + 1))
        expect(markers, `${language} ${key}`).toEqual(expected)
      }
    }
  })

  it('marks as verified only a passage with its act, and never an empty one', () => {
    for (const set of [QA_IT, QA_EN]) {
      for (const key of scenarios) {
        for (const c of set[key].citations) {
          if (c.verified) {
            expect(c.quote_snippet.length, key).toBeGreaterThan(20)
            expect(c.celex, key).toMatch(/^3\d{4}[RL]\d{4}$/)
          } else {
            // Not in the corpus: shown as "to be checked", with no quotation.
            expect(c.quote_snippet, key).toBe('')
          }
        }
      }
    }
  })

  it('answers the suggested questions with the right example, in each language', () => {
    const expected: DemoQAScenario[] = ['csrd', 'ai_act_art50', 'nis2', 'ai_act_art4']
    expect(SUGGESTED_QUESTIONS_IT.map(qaScenarioOf)).toEqual(expected)
    expect(SUGGESTED_QUESTIONS_EN.map(qaScenarioOf)).toEqual(expected)
  })

  it('routes questions about one article, two acts or the value chain', () => {
    expect(qaScenarioOf("Cosa dice l'art. 17 del GDPR?")).toBe('gdpr_art17')
    expect(qaScenarioOf("Articolo 9 dell'AI Act: cosa prevede?")).toBe('ai_act_art9')
    expect(qaScenarioOf('Art. 30 DORA: clausole contrattuali')).toBe('dora_art30')
    expect(qaScenarioOf('DORA e NIS2: quale si applica a una banca?')).toBe('cross_dora_nis2')
    expect(qaScenarioOf('Un cliente ci manda un questionario ESG: dobbiamo rispondere a tutto?')).toBe('value_chain')
    expect(qaScenarioOf('Serve un DPO?')).toBe('gdpr_dpo')
    // "ai" is an Italian preposition: it must not be read as "AI".
    expect(qaScenarioOf('Quali obblighi ha il titolare verso i dati personali dati ai fornitori?')).toBe('gdpr')
    // A number that is not an article number does not pick an article.
    expect(qaScenarioOf('Entro 30 giorni cosa chiede DORA?')).toBe('dora')
  })

  it('answers in the language asked for, with the fixed demo date', () => {
    const italian = getMockQAResponse(SUGGESTED_QUESTIONS_IT[0], 'it')
    const english = getMockQAResponse(SUGGESTED_QUESTIONS_IT[0], 'en')
    expect(italian.answer).toBe(QA_IT.csrd.answer)
    expect(english.answer).toBe(QA_EN.csrd.answer)
    expect(getMockQAResponse(SUGGESTED_QUESTIONS_IT[0]).answer).toBe(QA_IT.csrd.answer)
    expect(italian.corpus_as_of).toBe(DEMO_CORPUS_AS_OF)
    expect(english.corpus_as_of).toBe(DEMO_CORPUS_AS_OF)
  })

  it('says which consolidated text a passage of an amended act was read in', () => {
    const { citations } = getMockQAResponse('Cosa prevede la CSDDD sul dovere di diligenza?', 'it')
    expect(citations.length).toBeGreaterThan(0)
    for (const c of citations) expect(c.consolidated_as_of).toBe(DEMO_ACT_VERSIONS['32024L1760'])
    const gdpr = getMockQAResponse('Cosa prevede il GDPR?', 'it').citations
    for (const c of gdpr) expect(c.consolidated_as_of).toBeUndefined()
  })

  it('abstains on a question it has no example for', () => {
    for (const language of LANGUAGES) {
      const result = getMockQAResponse('Qual è la capitale della Francia?', language)
      expect(result.abstention_reason).toBe('demo_not_covered')
      expect(result.citations).toHaveLength(0)
      expect(result.suggested_questions?.length).toBeGreaterThan(0)
    }
    expect(getMockQAResponse('xyz', 'en').answer).not.toBe(getMockQAResponse('xyz', 'it').answer)
  })

  it('states the law as it stands after the 2026 amendments', () => {
    // CSRD: both thresholds, from financial years starting on 1 January 2027.
    expect(QA_IT.csrd.answer).toContain('1.000 dipendenti')
    expect(QA_IT.csrd.answer).toContain('450 milioni')
    expect(QA_IT.csrd.answer).toContain('1° gennaio 2027')
    // AI Act: high-risk dates moved by Regulation (EU) 2026/1744.
    expect(QA_IT.ai_act.answer).toContain('2 dicembre 2027')
    expect(QA_IT.ai_act.answer).toContain('2 agosto 2028')
    expect(JSON.stringify(QA_IT)).not.toContain('2 agosto 2027')
    // CSDDD: transposition 2028, application 2029.
    expect(QA_EN.csddd.answer).toContain('26 July 2028')
    expect(QA_EN.csddd.answer).toContain('26 July 2029')
  })
})

describe('demo copy', () => {
  it('uses no dash, ellipsis or curly quote characters', () => {
    const everything = JSON.stringify([
      DEMO_USER,
      DEMO_CLIENTS,
      getDemoAlerts('it'),
      getDemoAlerts('en'),
      QA_IT,
      QA_EN,
      BACKEND_FRAMEWORKS.flatMap((fw) => LANGUAGES.flatMap((l) => [undefined, SME, LARGE].map((p) => getMockGapAnalysis(fw, p, l)))),
      LANGUAGES.flatMap((l) => ['csrd', 'csddd', 'tassonomia', 'ai act', 'gdpr', 'nis2', 'dora', 'cra', '?'].flatMap((t) => [undefined, SME, LARGE].map((p) => getMockMonitorResponse(t, p, l)))),
    ])
    expect(everything.match(FORBIDDEN_CHARACTERS)?.[0]).toBeUndefined()
  })
})

describe('mockDelay', () => {
  it('resolves after the given time', async () => {
    const start = Date.now()
    await mockDelay(10)
    expect(Date.now() - start).toBeGreaterThanOrEqual(5)
  })
})
