import type { Metadata } from 'next'
import Link from 'next/link'
import { SiteHeader } from '@/components/site/SiteHeader'
import { SiteFooter } from '@/components/site/SiteFooter'
import { ButtonLink } from '@/components/ui/Button'

export const metadata: Metadata = {
  title: 'Metodo e trasparenza',
  description:
    'Come nasce una risposta di NormaAI: corpus EUR-Lex e Normattiva con data dichiarata, ricerca ibrida, controlli di aderenza alle fonti, astensione quando il testo non basta. Ogni affermazione rimanda al file del codice pubblico che la realizza.',
}

const REPO = 'https://github.com/Dan23RR/NormaAI'

/** Files of the public repository where a reader can check the claims above. */
function InCode({ paths }: { paths: string[] }) {
  return (
    <p className="mt-4 text-small text-ink-3">
      Nel codice:{' '}
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

// Acts in the acquisition list (CORE_FRAMEWORKS in src/crawler/eurlex/client.py).
const FRAMEWORKS: Array<{ name: string; acts: string }> = [
  {
    name: 'CSRD',
    acts: 'Dir. (UE) 2022/2464, ESRS (Reg. delegato (UE) 2023/2772), direttiva stop-the-clock (Dir. (UE) 2025/794) e Omnibus I (Dir. (UE) 2026/470)',
  },
  { name: 'CSDDD', acts: 'Dir. (UE) 2024/1760 e Omnibus I (Dir. (UE) 2026/470)' },
  { name: 'AI Act', acts: 'Reg. (UE) 2024/1689' },
  { name: 'DORA', acts: 'Reg. (UE) 2022/2554' },
  { name: 'NIS2', acts: 'Dir. (UE) 2022/2555' },
  { name: 'Tassonomia UE', acts: 'Reg. (UE) 2020/852' },
  { name: 'GDPR', acts: 'Reg. (UE) 2016/679' },
  {
    name: 'CRA',
    acts: 'Reg. (UE) 2024/2847 e Reg. di esecuzione (UE) 2025/2392, aggiunto per ultimo all’elenco',
  },
]

const PIPELINE: Array<{ title: string; body: string; paths: string[] }> = [
  {
    title: 'Recupero ibrido',
    body: 'La domanda viene cercata in due modi insieme: per significato, con vettori densi del modello multilingue paraphrase-multilingual-mpnet-base-v2 (768 dimensioni, scelto perché il corpus mescola l’inglese di EUR-Lex e l’italiano di Normattiva), e per termini esatti, con vettori sparsi in stile BM25 che catturano «articolo 29» o un numero CELEX. Le due classifiche sono fuse con Reciprocal Rank Fusion, senza pesi da tarare. I filtri escludono i testi superati e limitano la ricerca al corpus condiviso più i documenti dell’organizzazione.',
    paths: ['src/nlp/embedding/indexer.py', 'src/config.py'],
  },
  {
    title: 'Redazione dal testo recuperato',
    body: 'Il modello riceve la domanda, il profilo aziendale se inserito e i passaggi recuperati, con la consegna di citare atto e articolo e di non inventare atti o articoli che non esistono. Il testo dell’utente non entra mai nel prompt di sistema. Il modello predefinito è Google Gemini, configurabile.',
    paths: ['src/agents/nodes.py', 'prompts/qa_bot.txt', 'src/agents/sanitization.py'],
  },
  {
    title: 'Più campioni, una decisione',
    body: 'Per calibrare la fiducia, il sistema genera più risposte indipendenti (3 per impostazione predefinita) e le raggruppa per comportamento. Ne deriva un punteggio di fiducia calcolato, non autodichiarato dal modello: sopra 0,85 la risposta passa; sotto 0,50, o se nemmeno due campioni concordano, il sistema si astiene e lo scrive, chiedendo una revisione esperta. Se la migliore evidenza recuperata è debole (similarità densa sotto 0,25), la risposta viene comunque segnalata per revisione e la fiducia è limitata.',
    paths: ['src/agents/snc_node.py', 'src/agents/snc_layer.py', 'src/config.py'],
  },
  {
    title: 'Controllo di aderenza alle fonti',
    body: 'Ogni citazione della risposta è confrontata con i passaggi recuperati: la normativa, i numeri CELEX nel testo, il numero di articolo e la frase citata devono esistere nell’evidenza. Una citazione non supportata non blocca la risposta, ma la marca come «revisione esperta necessaria» e abbassa la fiducia. Il controllo gira sulla bozza e di nuovo sulla risposta effettivamente servita.',
    paths: ['src/agents/nodes.py', 'src/agents/snc_node.py'],
  },
  {
    title: 'Chain-of-Verification, su richiesta',
    body: 'Esiste una verifica a cinque fasi (estrazione delle affermazioni, domande di verifica, revisione, validazione dei riferimenti CELEX e URN contro EUR-Lex e Normattiva), ma è spenta per impostazione predefinita e si attiva per singola richiesta, solo per le risposte con fiducia sotto 0,85. Non è applicata a ogni risposta.',
    paths: ['src/config.py', 'src/agents/graph.py', 'src/agents/cove/orchestrator.py'],
  },
  {
    title: 'In lavorazione: verifica deterministica',
    body: 'Stiamo introducendo un controllo deterministico delle citazioni, cioè un confronto esatto del passaggio citato con il testo ufficiale indicizzato, che non dipende da un modello. Finché non è in produzione, in questa pagina resta un lavoro in corso, non un fatto.',
    paths: [],
  },
]

const CHOICES: Array<{ title: string; body: string; paths: string[] }> = [
  {
    title: 'Modello di embedding multilingue',
    body: 'Il modello di embedding solo inglese degradava la ricerca sul testo giuridico italiano. Il passaggio al modello multilingue ha richiesto di reindicizzare l’intero corpus, perché i vettori vivono in uno spazio specifico del modello.',
    paths: ['src/config.py'],
  },
  {
    title: 'Data del corpus dichiarata',
    body: 'Il corpus è congelato tra una reindicizzazione e l’altra, e lo stato «superato» di un atto viene impostato solo in quella fase. Finché il rilevamento delle abrogazioni non è automatico, la mitigazione onesta è dichiarare la data del corpus in ogni risposta e in ogni report.',
    paths: ['src/config.py', 'src/api/routers/intelligence.py', 'src/reports/generator.py'],
  },
  {
    title: 'Aggiornamento periodico spento',
    body: 'Un ciclo di acquisizione periodico esisteva sulla carta ma non girava davvero. Ora è esplicitamente spento per impostazione predefinita, finché un processo dedicato non lo gestisce: meglio una reindicizzazione esplicita e datata che un «aggiornato ogni notte» non vero.',
    paths: ['src/config.py', 'src/api/lifespan.py'],
  },
  {
    title: 'Chain-of-Verification opzionale',
    body: 'La verifica a cinque fasi aggiunge altre chiamate al modello per ogni risposta. È disponibile su richiesta, non promessa su tutto: i controlli sempre attivi sono il campionamento multiplo e l’aderenza alle fonti.',
    paths: ['src/config.py', 'src/agents/graph.py'],
  },
  {
    title: 'Cyber Resilience Act nell’elenco',
    body: 'Il CRA è stato aggiunto all’elenco di acquisizione con il regolamento di esecuzione sulle categorie di prodotto, annotando accanto ai CELEX le date di applicazione (obblighi di segnalazione dall’11 settembre 2026, applicazione piena dall’11 dicembre 2027).',
    paths: ['src/crawler/eurlex/client.py'],
  },
]

export default function MetodoPage() {
  return (
    <div className="min-h-screen bg-surface text-ink">
      <SiteHeader />

      <main>
        <section className="mx-auto max-w-site px-6 pb-14 pt-14 md:pt-20">
          <div className="max-w-prose">
            <h1 className="text-h1 md:text-display">Come nasce una risposta, e quando non arriva.</h1>
            <p className="mt-5 text-read text-ink-2">
              Pubblichiamo il metodo e il codice. Questa pagina descrive la pipeline così com&apos;è
              oggi, senza contatori e senza promesse: ogni sezione rimanda ai file del repository
              pubblico che la realizzano, così si può verificare invece di credere.
            </p>
          </div>
        </section>

        <section className="border-t border-rule">
          <div className="mx-auto max-w-site px-6 py-14">
            <h2 className="text-h2">Il corpus: testi ufficiali, con data</h2>
            <div className="mt-5 max-w-prose space-y-4 text-read text-ink-2">
              <p>
                Le fonti sono due: EUR-Lex, interrogato tramite l&apos;endpoint SPARQL
                dell&apos;Ufficio delle pubblicazioni dell&apos;Unione, e gli Open Data di Normattiva
                per il recepimento italiano. I testi vengono suddivisi per articolo e indicizzati;
                ogni frammento conserva atto (CELEX o URN), articolo, titolo della sezione e data.
              </p>
              <p>Gli atti nell&apos;elenco di acquisizione:</p>
              <ul className="list-disc space-y-1.5 pl-6">
                {FRAMEWORKS.map((f) => (
                  <li key={f.name}>
                    <strong className="font-semibold text-ink">{f.name}</strong>: {f.acts}
                  </li>
                ))}
              </ul>
              <p>
                Il corpus non si aggiorna da solo. Il ciclo periodico di acquisizione esiste nel
                codice ma è spento per impostazione predefinita: il corpus viene reindicizzato con
                operazioni esplicite, e la data di riferimento (
                <code className="font-mono text-small">corpus_as_of</code>) viene impostata al momento
                del deploy, restituita nei metadati di ogni risposta dell&apos;API e stampata a piè
                di pagina dei report. I testi superati da atti successivi sono esclusi dalla ricerca
                per impostazione predefinita.
              </p>
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
            <h2 className="text-h2">La pipeline, passo per passo</h2>
            <p className="mt-5 max-w-prose text-read text-ink-2">
              Ogni domanda attraversa questi passaggi nell&apos;ordine. I numeri citati sono le
              soglie impostate nel codice, non risultati misurati.
            </p>
            <ol className="mt-8 max-w-prose list-decimal space-y-8 pl-6">
              {PIPELINE.map((step) => (
                <li key={step.title}>
                  <h3 className="text-h3">{step.title}</h3>
                  <p className="mt-2 text-read text-ink-2">{step.body}</p>
                  {step.paths.length > 0 && <InCode paths={step.paths} />}
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="border-t border-rule">
          <div className="mx-auto max-w-site px-6 py-14">
            <h2 className="text-h2">Cosa vede chi legge</h2>
            <ul className="mt-5 max-w-prose list-disc space-y-2 pl-6 text-read text-ink-2">
              <li>L&apos;atto e l&apos;articolo citati, il passaggio riportato e il link al testo ufficiale.</li>
              <li>Un livello di affidabilità espresso a parole, non una percentuale.</li>
              <li>
                Il segnale «revisione esperta necessaria» quando il sistema si astiene, trova
                evidenza debole o una citazione non supportata.
              </li>
              <li>
                L&apos;avviso che le risposte sono generate da un sistema di intelligenza
                artificiale (Reg. (UE) 2024/1689, art. 50): nel piè di pagina
                dell&apos;applicazione, nella pagina Chiedi e nei report.
              </li>
            </ul>
            <InCode
              paths={[
                'frontend/src/app/dashboard/qa/page.tsx',
                'frontend/src/components/app/AppShell.tsx',
                'src/reports/generator.py',
              ]}
            />
          </div>
        </section>

        <section className="border-t border-rule">
          <div className="mx-auto max-w-site px-6 py-14">
            <h2 className="text-h2">Dati e separazione tra organizzazioni</h2>
            <div className="mt-5 max-w-prose space-y-4 text-read text-ink-2">
              <p>
                Il sito è su Vercel (regione di Francoforte); l&apos;API e i database su un server
                Hetzner in Germania. Ogni organizzazione vede solo i propri dati: Row Level
                Security in PostgreSQL con un ruolo non superuser, chiavi di cache per
                organizzazione, filtro per organizzazione nel motore di ricerca.
                L&apos;amministratore può esportare e cancellare i dati dell&apos;organizzazione
                dall&apos;applicazione.
              </p>
              <p>
                I dettagli, e ciò che manca ancora (SSO, certificazioni, penetration test), sono
                nella pagina{' '}
                <Link href="/security" className="text-union hover:underline">
                  Sicurezza
                </Link>
                .
              </p>
            </div>
          </div>
        </section>

        <section className="border-t border-rule">
          <div className="mx-auto max-w-site px-6 py-14">
            <h2 className="text-h2">Come verifichiamo il codice</h2>
            <div className="mt-5 max-w-prose space-y-4 text-read text-ink-2">
              <p>
                A ogni push: lint e formato (ruff), type-check (mypy, bloccante sui moduli di
                sicurezza), test del backend su PostgreSQL, Qdrant e Redis reali, compreso un test
                con due organizzazioni che blocca la build se una vede i dati dell&apos;altra;
                type-check, test e build del frontend; CodeQL, Gitleaks, Bandit, Trivy e una SBOM.
              </p>
              <p>
                I conteggi dei test cambiano a ogni commit: per questo non li stampiamo qui. Si
                leggono nell&apos;ultima esecuzione della CI sul repository.
              </p>
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
            <h2 className="text-h2">Scelte che si leggono nel codice</h2>
            <p className="mt-5 max-w-prose text-read text-ink-2">
              Le decisioni che contano sono annotate accanto al codice che le realizza, anche
              quando correggono un errore nostro.
            </p>
            <ul className="mt-8 max-w-prose space-y-8">
              {CHOICES.map((c) => (
                <li key={c.title} className="border-t border-rule pt-6">
                  <h3 className="text-h3">{c.title}</h3>
                  <p className="mt-2 text-read text-ink-2">{c.body}</p>
                  <InCode paths={c.paths} />
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="border-t border-rule bg-surface-2">
          <div className="mx-auto max-w-site px-6 py-14">
            <h2 className="text-h2">Giudica il metodo su una domanda vera.</h2>
            <p className="mt-4 max-w-prose text-read text-ink-2">
              Porta un caso reale del tuo lavoro. Se la risposta, citazioni alla mano, non è
              migliore della tua ricerca attuale, finisce lì.
            </p>
            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <ButtonLink href="mailto:info@normaai.org?subject=NormaAI%20demo">
                Scrivi per una demo
              </ButtonLink>
              <ButtonLink href="/#codex" variant="secondary">
                Scarica il Codex Post-Omnibus
              </ButtonLink>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  )
}
