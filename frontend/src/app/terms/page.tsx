import { LegalLayout, LegalSection } from '@/components/LegalLayout'

export const metadata = {
  title: 'Termini di Servizio',
}

export default function TermsPage() {
  return (
    <LegalLayout
      title="Termini di Servizio"
      intro="Condizioni d'uso di NormaAI: natura del servizio, avviso sul sistema di intelligenza artificiale (art. 50 AI Act), limitazione di responsabilità ed esclusione di garanzia."
      lastUpdated="23 ottobre 2026"
    >
      <LegalSection title="1. Natura del servizio">
        <p>
          NormaAI è un servizio gestito da Daniel Culotta, persona fisica, Inverigo (CO), Italia,
          nell&apos;ambito di un progetto non ancora costituito in società. Contatti:{' '}
          <a href="mailto:info@normaai.org">info@normaai.org</a>.
        </p>
        <p>
          NormaAI fornisce analisi automatizzate basate su intelligenza artificiale a scopo
          esclusivamente informativo e di supporto decisionale in materia di conformità normativa
          europea. Il servizio{' '}
          <strong>non costituisce consulenza legale, fiscale o professionale</strong>.
        </p>
        <p>
          La modalità &quot;Demo con dati di esempio&quot; usa dati fittizi, non interroga il corpus
          reale ed è segnalata in ogni pagina dell&apos;applicazione.
        </p>
      </LegalSection>

      <LegalSection title="2. Sistema di intelligenza artificiale (art. 50 AI Act)">
        <p>Ai sensi dell&apos;art. 50 del Regolamento (UE) 2024/1689 (AI Act) ti informiamo che:</p>
        <ul>
          <li>usando NormaAI interagisci con un sistema di intelligenza artificiale, non con una persona;</li>
          <li>
            le risposte, le verifiche di ambito, le gap analysis, gli avvisi e i report sono
            generati automaticamente da un modello linguistico (Google Gemini per impostazione
            predefinita) a partire dai testi normativi recuperati dal corpus. Nessuno li scrive o
            li rivede prima che ti vengano mostrati;
          </li>
          <li>
            ogni risposta indica le fonti citate (atto, articolo, passaggio) e un livello di
            affidabilità. Quando il sistema non trova sostegno sufficiente nel corpus, lo dichiara
            e segnala la necessità di una revisione esperta invece di rispondere;
          </li>
          <li>
            le risposte possono contenere errori, omissioni o citazioni imprecise. Verifica sempre
            il testo ufficiale su EUR-Lex o Normattiva e consulta un professionista prima di
            prendere decisioni.
          </li>
        </ul>
        <p>Lo stesso avviso è riportato nell&apos;applicazione e nei report generati.</p>
      </LegalSection>

      <LegalSection title="3. Limitazione di responsabilità">
        <p>
          Il gestore del servizio non sarà in alcun caso responsabile per: (a) decisioni prese
          dall&apos;Utente sulla base degli output del sistema; (b) sanzioni, multe o danni
          derivanti dalla non conformità normativa; (c) errori, omissioni o imprecisioni nelle
          analisi generate; (d) mancato aggiornamento delle informazioni normative.
        </p>
        <p>
          La responsabilità complessiva del gestore del servizio è in ogni caso limitata
          all&apos;importo dei corrispettivi pagati dall&apos;Utente nei 12 mesi precedenti
          l&apos;evento generatore del danno.
        </p>
      </LegalSection>

      <LegalSection title="4. Esclusione di garanzia">
        <p>
          NormaAI non garantisce che l&apos;utilizzo del servizio assicuri la conformità
          dell&apos;Utente ai requisiti normativi applicabili. I punteggi di conformità, le analisi
          di gap e le raccomandazioni sono stime basate su modelli di intelligenza artificiale e
          possono non riflettere lo stato effettivo di conformità. L&apos;Utente è l&apos;unico
          responsabile delle proprie decisioni di compliance.
        </p>
      </LegalSection>

      <LegalSection title="5. Aggiornamento normativo">
        <p>
          Le informazioni normative contenute nel sistema sono aggiornate alla data
          dell&apos;ultima indicizzazione del corpus. Il corpus non si aggiorna da solo: viene
          reindicizzato con operazioni esplicite, e la data di riferimento è riportata nei
          metadati delle risposte dell&apos;API e nei report in PDF. NormaAI si impegna a mantenere
          aggiornate le informazioni ma non garantisce la completezza, l&apos;accuratezza o la
          tempestività degli aggiornamenti.
        </p>
      </LegalSection>

      <LegalSection title="6. Dati personali e sicurezza">
        <p>
          Il trattamento dei dati personali è descritto nella{' '}
          <a href="/privacy">Privacy Policy</a>; le misure di sicurezza presenti nel codice, e
          quelle che mancano ancora, nella pagina <a href="/security">Sicurezza</a>.
        </p>
      </LegalSection>

      <LegalSection title="7. Codice sorgente">
        <p>
          Il codice di NormaAI è pubblicato su{' '}
          <a href="https://github.com/Dan23RR/NormaAI" target="_blank" rel="noopener noreferrer">
            GitHub
          </a>{' '}
          con licenza MIT. La licenza riguarda il codice sorgente, non il servizio ospitato né i
          suoi contenuti.
        </p>
      </LegalSection>

      <LegalSection title="8. Modifiche">
        <p>
          Le modifiche a questi termini sono pubblicate su questa pagina con la nuova data di
          aggiornamento.
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
