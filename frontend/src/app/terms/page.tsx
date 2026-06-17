import { LegalLayout, LegalSection } from '@/components/LegalLayout'

export const metadata = {
  title: 'Termini di Servizio - NormaAI',
}

export default function TermsPage() {
  return (
    <LegalLayout
      title="Termini di Servizio"
      intro="Condizioni d'uso di NormaAI. Disclaimer AI Act, limitazione di responsabilità, esclusione di garanzia."
      lastUpdated="Marzo 2026 · NormaAI v0.3"
    >
      <LegalSection title="1. Natura del Servizio">
        <p>
          NormaAI fornisce analisi automatizzate basate su intelligenza artificiale a scopo
          esclusivamente informativo e di supporto decisionale in materia di conformità
          normativa europea. Il servizio{' '}
          <strong className="text-night">non costituisce consulenza legale, fiscale o professionale</strong>.
        </p>
      </LegalSection>

      <LegalSection title="2. Sistema di Intelligenza Artificiale">
        <p>
          Ai sensi dell&apos;Art. 50 del Regolamento UE 2024/1689 (AI Act), si informa che
          NormaAI utilizza modelli di intelligenza artificiale generativa (Google Gemini) per
          elaborare le risposte. Tutti gli output sono generati automaticamente da AI e
          possono contenere imprecisioni.
        </p>
      </LegalSection>

      <LegalSection title="3. Limitazione di Responsabilità">
        <p>
          NormaAI S.r.l. non sarà in alcun caso responsabile per: (a) decisioni prese
          dall&apos;Utente sulla base degli output del sistema; (b) sanzioni, multe o danni
          derivanti dalla non conformità normativa; (c) errori, omissioni o imprecisioni nelle
          analisi generate; (d) mancato aggiornamento delle informazioni normative.
        </p>
        <p>
          La responsabilità complessiva di NormaAI S.r.l. è in ogni caso limitata
          all&apos;importo dei corrispettivi pagati dall&apos;Utente nei 12 mesi precedenti
          l&apos;evento generatore del danno.
        </p>
      </LegalSection>

      <LegalSection title="4. Esclusione di Garanzia">
        <p>
          NormaAI non garantisce che l&apos;utilizzo del servizio assicuri la conformità
          dell&apos;Utente ai requisiti normativi applicabili. Gli score di conformità, le
          analisi di gap e le raccomandazioni sono stime basate su modelli di intelligenza
          artificiale e possono non riflettere lo stato effettivo di conformità. L&apos;Utente
          è l&apos;unico responsabile delle proprie decisioni di compliance.
        </p>
      </LegalSection>

      <LegalSection title="5. Aggiornamento Normativo">
        <p>
          Le informazioni normative contenute nel sistema sono aggiornate alla data
          dell&apos;ultimo aggiornamento della knowledge base. NormaAI si impegna a mantenere
          aggiornate le informazioni ma non garantisce la completezza, accuratezza o
          tempestività degli aggiornamenti.
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
