import { LegalLayout, LegalSection } from '@/components/LegalLayout'

export const metadata = {
  title: 'Privacy Policy — NormaAI',
}

export default function PrivacyPage() {
  return (
    <LegalLayout
      title="Privacy Policy"
      intro="Come NormaAI tratta i dati aziendali necessari all'erogazione del servizio, ai sensi del GDPR."
      lastUpdated="Marzo 2026 · NormaAI v0.3"
    >
      <LegalSection title="1. Titolare e Responsabile del Trattamento">
        <p>
          L&apos;Utente (Titolare del trattamento) affida a NormaAI S.r.l. (Responsabile del
          trattamento) il trattamento dei dati aziendali necessari all&apos;erogazione del
          servizio, ai sensi dell&apos;Art. 28 GDPR.
        </p>
      </LegalSection>

      <LegalSection title="2. Dati Trattati">
        <ul className="list-disc space-y-1 pl-5">
          <li>Profili aziendali (settore, dimensione, fatturato, giurisdizioni)</li>
          <li>Query di compliance e cronologia conversazioni</li>
          <li>Documenti caricati per analisi</li>
          <li>Metadati di utilizzo del servizio</li>
        </ul>
      </LegalSection>

      <LegalSection title="3. Base Giuridica e Finalità">
        <p>
          I dati sono trattati sulla base della necessità contrattuale (Art. 6(1)(b) GDPR) per
          la sola finalità di erogazione del servizio di analisi di conformità normativa.
          Nessun dato viene condiviso con terzi per finalità diverse dal servizio.
        </p>
      </LegalSection>

      <LegalSection title="3-bis. Prospecting e marketing diretto B2B">
        <p>
          Per le sole comunicazioni commerciali B2B (outbound), NormaAI tratta dati di contatto
          professionali (nome, ruolo, email aziendale, organizzazione) raccolti da fonti pubbliche
          e professionali, sulla base del <strong className="text-night">legittimo interesse</strong>{' '}
          al marketing diretto (Art. 6(1)(f) GDPR, Considerando 47). L&apos;interessato può opporsi
          in qualsiasi momento e senza oneri (Art. 21), rispondendo &laquo;STOP&raquo; o scrivendo a{' '}
          <a href="mailto:privacy@normaai.org" className="text-clay transition hover:text-clay-deep">
            privacy@normaai.org
          </a>
          ; ogni email include inoltre un header di disiscrizione (List-Unsubscribe). I contatti che
          si oppongono o non rispondono sono inseriti in una lista di soppressione e non più contattati.
        </p>
      </LegalSection>

      <LegalSection title="4. Sub-Responsabili del Trattamento">
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong className="text-night">Google LLC</strong> (Gemini API) — elaborazione query
            AI. Trasferimenti USA coperti da Standard Contractual Clauses (SCC) e Data Privacy
            Framework (DPF).
          </li>
          <li>
            <strong className="text-night">Resend, Inc.</strong> (USA) — invio di email transazionali
            e di servizio (outbound). Trasferimenti coperti da SCC.
          </li>
          <li>
            <strong className="text-night">Google Workspace / Gmail</strong> (USA) — casella di posta
            per la gestione delle risposte (inbound). Coperto da DPF/SCC.
          </li>
          <li>
            <strong className="text-night">Hetzner Online GmbH</strong> (Germania, UE) — hosting
            applicativo e database con data residency UE; nessun trasferimento extra-UE.
          </li>
        </ul>
      </LegalSection>

      <LegalSection title="5. Conservazione">
        <p>
          I dati sono conservati per la durata del contratto di servizio. Al termine, i dati
          vengono cancellati entro 90 giorni, salvo obblighi di legge.
        </p>
      </LegalSection>

      <LegalSection title="6. Diritti dell'Interessato">
        <p>
          L&apos;Utente può esercitare i diritti di accesso, rettifica, cancellazione,
          limitazione, portabilità e opposizione scrivendo a{' '}
          <a
            href="mailto:privacy@normaai.org"
            className="text-clay transition hover:text-clay-deep"
          >
            privacy@normaai.org
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection title="7. Trasparenza AI (Art. 50 AI Act)">
        <p>
          NormaAI utilizza il modello Gemini 2.5 Flash (Google) per generare analisi normative.
          La knowledge base contiene testi di 7 framework normativi EU (CSRD, CSDDD, AI Act,
          DORA, NIS2, EU Taxonomy, GDPR). Tutti gli output sono generati da intelligenza
          artificiale e richiedono verifica da parte di professionisti qualificati.
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
