import Link from 'next/link'
import { CheckCircle2 } from 'lucide-react'
import { SiteHeader } from '@/components/site/SiteHeader'
import { SiteFooter } from '@/components/site/SiteFooter'
import { CodexForm } from '@/components/site/CodexForm'
import { ButtonLink } from '@/components/ui/Button'
import { Badge, FrameworkBadge } from '@/components/ui/Badge'
import { LawQuote } from '@/components/ui/LawQuote'
import { Table, THead, TBody, TR, TH, TD } from '@/components/ui/Table'
import { eurlexUrl } from '@/lib/sources'

// Public landing page. Every claim here must be true of the code as it ships
// (see DESIGN.md, "stati onesti"). The hero shows the product's signature
// element: an answer with the passage of law that supports it.

const ACTS: Array<{ framework: string; act: string; covers: string }> = [
  {
    framework: 'CSRD',
    act: 'Direttiva (UE) 2022/2464, modificata dalla Direttiva (UE) 2026/470 (Omnibus I); D.Lgs. 125/2024',
    covers: 'Rendicontazione di sostenibilità: soglie, calendario, principi ESRS',
  },
  {
    framework: 'CSDDD',
    act: 'Direttiva (UE) 2024/1760, modificata dalla Direttiva (UE) 2026/470',
    covers: 'Dovere di diligenza: recepimento entro il 26 luglio 2028, prima applicazione nel 2029',
  },
  {
    framework: 'AI_ACT',
    act: 'Regolamento (UE) 2024/1689',
    covers: 'Obblighi per fornitori e deployer, trasparenza (art. 50), sistemi ad alto rischio',
  },
  {
    framework: 'NIS2',
    act: 'Direttiva (UE) 2022/2555; D.Lgs. 138/2024',
    covers: 'Soggetti essenziali e importanti, misure di sicurezza, notifica degli incidenti',
  },
  {
    framework: 'DORA',
    act: 'Regolamento (UE) 2022/2554',
    covers: 'Resilienza operativa digitale del settore finanziario, rischio ICT e fornitori terzi',
  },
  {
    framework: 'GDPR',
    act: 'Regolamento (UE) 2016/679',
    covers: 'Protezione dei dati personali, basi giuridiche, diritti degli interessati',
  },
  {
    framework: 'TAXONOMY',
    act: 'Regolamento (UE) 2020/852',
    covers: 'Attività economiche ecosostenibili e obblighi di informativa',
  },
  {
    framework: 'CRA',
    act: 'Regolamento (UE) 2024/2847',
    covers: 'Cybersicurezza dei prodotti con elementi digitali',
  },
  {
    framework: 'ESRS',
    act: 'Regolamento delegato (UE) 2023/2772',
    covers: 'Principi di rendicontazione di sostenibilità (Set 1)',
  },
]

function AnswerExample() {
  return (
    <figure className="rounded-xl border border-rule bg-surface shadow-doc">
      <figcaption className="flex items-center justify-between border-b border-rule px-5 py-3 text-caption text-ink-3">
        <span>Esempio di risposta</span>
        <span>Fonte: testo ufficiale su EUR-Lex</span>
      </figcaption>
      <div className="px-5 py-5">
        <p className="text-small text-ink-3">Domanda</p>
        <p className="mt-1 text-read text-ink">
          Un assistente virtuale che risponde ai clienti sul nostro sito deve dichiarare che è
          un&rsquo;intelligenza artificiale?
        </p>
        <p className="mt-5 text-small text-ink-3">Risposta</p>
        <p className="mt-1 text-read text-ink">
          Sì. L&rsquo;articolo 50, paragrafo 1, del Regolamento (UE) 2024/1689 obbliga chi fornisce un
          sistema di IA destinato a interagire con le persone a progettarlo in modo che le persone
          sappiano di parlare con un&rsquo;IA, salvo che sia evidente dal contesto{' '}
          <a href="#esempio-fonte-1" className="font-medium text-union">
            [1]
          </a>
          . L&rsquo;obbligo si applica dal 2 agosto 2026{' '}
          <a href="#esempio-fonte-2" className="font-medium text-union">
            [2]
          </a>
          .
        </p>
        <div className="mt-5 space-y-4 border-t border-rule pt-5">
          <div id="esempio-fonte-1">
            <LawQuote
              quote="siano informate del fatto che stanno interagendo con un sistema di IA"
              before="I fornitori garantiscono che i sistemi di IA destinati a interagire direttamente con le persone fisiche sono progettati e sviluppati in modo tale che le persone fisiche interessate"
              after="a meno che ciò non risulti evidente dal punto di vista di una persona fisica ragionevolmente informata, attenta e avveduta"
              act="Regolamento (UE) 2024/1689"
              article="art. 50, par. 1"
              celex="32024R1689"
              url={eurlexUrl('32024R1689')}
              origin="EUR-Lex"
            />
          </div>
          <p id="esempio-fonte-2" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small text-ink-2">
            <span>
              <span className="font-medium text-ink">Regolamento (UE) 2024/1689</span>, art. 113
            </span>
            <span className="inline-flex items-center gap-1 text-ok">
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              Verificata
            </span>
            <span>applicazione dal 2 agosto 2026</span>
          </p>
        </div>
      </div>
    </figure>
  )
}

export default function Home() {
  return (
    <div className="min-h-screen bg-surface text-ink">
      <SiteHeader />

      {/* Hero */}
      <section className="mx-auto max-w-site px-6 pb-20 pt-14 md:pt-20">
        <div className="grid gap-12 lg:grid-cols-12 lg:items-start">
          <div className="lg:col-span-6 lg:pt-6">
            <h1 className="text-display md:text-display-lg">
              Ogni risposta sul diritto UE, con il passaggio di legge che la sostiene.
            </h1>
            <p className="mt-6 max-w-prose text-read text-ink-2 md:text-h4 md:font-normal">
              NormaAI risponde su CSRD, CSDDD, AI Act, NIS2, DORA, GDPR e Tassonomia citando l&rsquo;atto e
              l&rsquo;articolo, con il testo ufficiale di EUR-Lex e Normattiva a un clic. Quando il testo non
              basta, lo dice.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonLink href="#demo" size="lg">
                Richiedi una demo
              </ButtonLink>
              <ButtonLink href="/scope-csrd.html" variant="secondary" size="lg">
                Verifica se sei in ambito CSRD
              </ButtonLink>
            </div>
            <p className="mt-5 text-small text-ink-3">
              Accesso su invito durante i pilot. Codice aperto. Data del corpus dichiarata in ogni risposta.
            </p>
          </div>
          <div className="lg:col-span-6">
            <AnswerExample />
          </div>
        </div>
      </section>

      {/* Come funziona */}
      <section id="come-funziona" className="border-t border-rule">
        <div className="mx-auto max-w-site px-6 py-20">
          <h2 className="max-w-3xl text-h1 md:text-display">Tre strumenti, una regola: niente senza fonte.</h2>
          <div className="mt-12 grid gap-10 md:grid-cols-3 md:gap-0 md:divide-x md:divide-rule">
            <div className="md:pr-8">
              <h3 className="text-h3">Chiedi</h3>
              <p className="mt-3 text-body text-ink-2">
                Domande in italiano o inglese. La risposta cita atto, articolo e passaggio, mostra per ogni
                citazione se il passaggio è stato ritrovato nel testo ufficiale e porta al testo con un
                clic. Se il corpus non copre la domanda, NormaAI si astiene e lo dice.
              </p>
              <ul className="mt-4 space-y-1.5 text-small text-ink-2">
                <li>Profilo aziendale opzionale per risposte sul vostro caso</li>
                <li>Astensione dichiarata invece di una risposta inventata</li>
                <li>Data del corpus in ogni risposta</li>
              </ul>
            </div>
            <div className="md:px-8">
              <h3 className="text-h3">Ambito</h3>
              <p className="mt-3 text-body text-ink-2">
                Dimensione, settore, Paese: quali obblighi si applicano all&rsquo;azienda e da quando, con la
                norma che lo stabilisce. Oggi disponibile come verifica gratuita per la CSRD e per
                l&rsquo;articolo 50 dell&rsquo;AI Act.
              </p>
              <ul className="mt-4 space-y-1.5 text-small">
                <li>
                  <Link href="/scope-csrd.html" className="text-union hover:underline">
                    Verifica CSRD dopo l&rsquo;Omnibus I
                  </Link>
                </li>
                <li>
                  <Link href="/scope-aiact.html" className="text-union hover:underline">
                    Verifica AI Act, articolo 50
                  </Link>
                </li>
              </ul>
            </div>
            <div className="md:pl-8">
              <div className="flex items-center gap-2">
                <h3 className="text-h3">Monitoraggio</h3>
                <Badge tone="warn">In sviluppo</Badge>
              </div>
              <p className="mt-3 text-body text-ink-2">
                Il calendario degli obblighi dei vostri clienti e le novità normative, ciascuna con la
                data in cui è stata verificata. Disponibile ai partecipanti ai pilot man mano che viene
                completato.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Fonti */}
      <section id="fonti" className="border-t border-rule bg-surface-2">
        <div className="mx-auto max-w-site px-6 py-20">
          <div className="max-w-3xl">
            <h2 className="text-h1 md:text-display">I testi da cui partono le risposte.</h2>
            <p className="mt-5 text-read text-ink-2">
              Gli atti vengono da EUR-Lex, la banca dati ufficiale del diritto dell&rsquo;Unione, e da
              Normattiva per il recepimento italiano. Il corpus ha una data, mostrata in ogni risposta;
              le versioni consolidate e italiane degli atti sono in corso di inserimento.
            </p>
          </div>
          <div className="mt-10">
            <Table>
              <THead>
                <TR>
                  <TH>Ambito</TH>
                  <TH>Atti</TH>
                  <TH className="hidden md:table-cell">Cosa copre</TH>
                </TR>
              </THead>
              <TBody>
                {ACTS.map((row) => (
                  <TR key={row.framework}>
                    <TD className="whitespace-nowrap">
                      <FrameworkBadge framework={row.framework} />
                    </TD>
                    <TD>
                      <span className="font-serif text-read">{row.act}</span>
                      <span className="mt-1 block text-small text-ink-2 md:hidden">{row.covers}</span>
                    </TD>
                    <TD className="hidden text-ink-2 md:table-cell">{row.covers}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>
        </div>
      </section>

      {/* Metodo */}
      <section className="border-t border-rule">
        <div className="mx-auto grid max-w-site gap-12 px-6 py-20 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <h2 className="text-h1 md:text-display">Perché puoi fidarti di una citazione.</h2>
            <p className="mt-5 text-read text-ink-2">
              Un modello linguistico, da solo, inventa riferimenti plausibili. NormaAI lo costringe a
              lavorare sul testo di legge e a mostrare il lavoro.
            </p>
            <Link href="/metodo" className="mt-6 inline-block text-body font-medium text-union hover:underline">
              Il metodo nel dettaglio
            </Link>
          </div>
          <ol className="space-y-6 lg:col-span-7">
            {[
              {
                title: 'Recupero dal testo ufficiale',
                body: 'La domanda cerca i passaggi pertinenti negli atti indicizzati, per significato e per parole esatte, con la data del corpus dichiarata.',
              },
              {
                title: 'Risposta ancorata ai passaggi',
                body: 'Il modello risponde solo a partire dai passaggi recuperati e cita per atto e articolo; il testo citato resta visibile accanto alla risposta.',
              },
              {
                title: 'Verifica di ogni citazione',
                body: 'Ogni citazione mostra se il passaggio è stato ritrovato nel testo ufficiale. Se non lo è, viene segnata come da verificare, non nascosta.',
              },
              {
                title: 'Astensione quando serve',
                body: 'Se i passaggi recuperati non bastano, NormaAI dice che non può rispondere e suggerisce dove guardare, invece di completare con un’invenzione.',
              },
            ].map((step, i) => (
              <li key={step.title} className="flex gap-5">
                <span className="mt-0.5 font-serif text-h2 tabular text-ink-3" aria-hidden="true">
                  {i + 1}
                </span>
                <div>
                  <h3 className="text-h3">{step.title}</h3>
                  <p className="mt-2 text-body text-ink-2">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Per chi */}
      <section className="border-t border-rule bg-surface-2">
        <div className="mx-auto max-w-site px-6 py-20">
          <h2 className="max-w-3xl text-h1 md:text-display">
            Per chi deve rispondere con l&rsquo;articolo, non con un&rsquo;opinione.
          </h2>
          <div className="mt-12 grid gap-10 md:grid-cols-3">
            {[
              {
                who: 'Compliance officer',
                text: 'Una persona, sette ambiti normativi. Quando la direzione chiede "siamo a posto?", la risposta deve avere l’articolo accanto.',
              },
              {
                who: 'Consulenti e studi',
                text: 'Offrite compliance UE ai clienti senza un partner senior per ogni materia: la base normativa verificata la mette NormaAI, la valutazione e la firma restano vostre.',
              },
              {
                who: 'PMI e direzione finanziaria',
                text: 'Capire se un obbligo vi riguarda, da quando e cosa comporta, prima di decidere dove spendere.',
              },
            ].map((p) => (
              <div key={p.who}>
                <h3 className="text-h3">{p.who}</h3>
                <p className="mt-3 text-body text-ink-2">{p.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Codex */}
      <section id="codex" className="border-t border-rule">
        <div className="mx-auto grid max-w-site gap-12 px-6 py-20 lg:grid-cols-12 lg:items-start">
          <div className="lg:col-span-7">
            <p className="text-small text-ink-3">Guida gratuita in PDF, 17 pagine</p>
            <h2 className="mt-2 text-h1 md:text-display">Codex Post-Omnibus 2025-2029</h2>
            <p className="mt-5 max-w-prose text-read text-ink-2">
              La guida operativa per chi gestisce CSRD, CSDDD e Tassonomia dopo l&rsquo;Omnibus I: chi resta
              in ambito, il calendario fino al 2029, cosa resta dei principi ESRS, gli errori più comuni
              nelle prime rendicontazioni.
            </p>
            <ul className="mt-6 space-y-2.5 text-body text-ink-2">
              {[
                'Diagramma "sono in ambito?" per CSRD, CSDDD e Tassonomia',
                'ESRS Set 1: cosa resta dopo la riduzione dei datapoint',
                'Standard volontario VSME: quando conviene adottarlo',
                'Calendario 2026-2029 con recepimenti e prime rendicontazioni',
              ].map((item) => (
                <li key={item} className="flex items-start gap-2.5">
                  <CheckCircle2 className="mt-1 h-4 w-4 shrink-0 text-ok" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div className="lg:col-span-5">
            <CodexForm />
          </div>
        </div>
      </section>

      {/* Demo */}
      <section id="demo" className="bg-[#0C1B33] text-[#E8ECF3]">
        <div className="mx-auto max-w-3xl px-6 py-24 text-center">
          <h2 className="text-h1 text-white md:text-display">Porta una domanda vera. Trenta minuti, senza impegno.</h2>
          <p className="mx-auto mt-5 max-w-xl text-read text-[#B3BCCB]">
            Mostriamo NormaAI sul vostro caso. Se la risposta non è migliore della ricerca che fate oggi,
            finisce lì. Se lo è, parliamo di un pilot.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a
              href="mailto:info@normaai.org?subject=NormaAI%20demo&body=Buongiorno%2C%0A%0Avorrei%20vedere%20NormaAI%20su%20un%20caso%20reale.%0A%0AOrganizzazione%3A%0ARuolo%3A%0ADisponibilit%C3%A0%3A%0A%0AGrazie."
              className="inline-flex h-12 items-center justify-center rounded-md bg-white px-6 text-read font-medium text-[#0C1B33] no-underline transition-colors hover:bg-[#E8ECF3]"
            >
              Scrivi a info@normaai.org
            </a>
            <Link
              href="/login"
              className="inline-flex h-12 items-center justify-center rounded-md border border-white/30 px-6 text-read font-medium text-white no-underline transition-colors hover:border-white/60"
            >
              Hai già un account? Accedi
            </Link>
          </div>
        </div>
      </section>

      <SiteFooter />
    </div>
  )
}
