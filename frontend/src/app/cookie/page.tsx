import { LegalLayout, LegalSection } from '@/components/LegalLayout'

export const metadata = {
  title: 'Cookie Policy',
}

type StorageRow = { key: string; purpose: string; duration: string }

// Keys verified against frontend/src (grep localStorage / sessionStorage).
const LOCAL_STORAGE: StorageRow[] = [
  {
    key: 'normaai_access_token',
    purpose: "Token di accesso (JWT) all'area riservata.",
    duration: 'Fino al logout; il token scade dopo 60 minuti e viene rinnovato.',
  },
  {
    key: 'normaai_refresh_token',
    purpose: 'Token di rinnovo della sessione.',
    duration: 'Fino al logout; validità 7 giorni.',
  },
  {
    key: 'normaai_demo_mode',
    purpose: 'Segnala che stai usando la demo con dati di esempio.',
    duration: "Fino all'uscita dalla demo o al logout.",
  },
  {
    key: 'normaai_locale',
    purpose: "Lingua dell'interfaccia (italiano o inglese).",
    duration: 'Finché non la cancelli.',
  },
  {
    key: 'normaai.theme',
    purpose: "Tema chiaro o scuro scelto nell'applicazione.",
    duration: 'Finché non la cancelli.',
  },
  {
    key: 'normaai.cookie-banner.dismissed',
    purpose: "Ricorda che hai chiuso l'informativa sui cookie.",
    duration: 'Finché non la cancelli.',
  },
  {
    key: 'normaai_sidebar_collapsed',
    purpose: 'Stato (aperta o compressa) della barra laterale.',
    duration: 'Finché non la cancelli.',
  },
  {
    key: 'normaai_alert_prefs',
    purpose: 'Filtri scelti nella pagina degli avvisi (gravità, normativa, letti o non letti).',
    duration: 'Finché non la cancelli.',
  },
  {
    key: 'normaai_qa_language',
    purpose: 'Lingua delle risposte nella pagina Chiedi.',
    duration: 'Finché non la cancelli.',
  },
]

const SESSION_STORAGE: StorageRow[] = [
  {
    key: 'normaai_company_profile',
    purpose: 'Profilo aziendale compilato nei moduli, per non doverlo reinserire.',
    duration: 'Chiusura della scheda.',
  },
  {
    key: 'normaai_qa_messages',
    purpose: 'Conversazione corrente della pagina Chiedi.',
    duration: 'Chiusura della scheda.',
  },
  {
    key: 'normaai_gap_result',
    purpose: 'Ultimo risultato di gap analysis.',
    duration: 'Chiusura della scheda.',
  },
  {
    key: 'normaai_gap_scores',
    purpose: 'Punteggi per framework usati nei grafici di analisi.',
    duration: 'Chiusura della scheda.',
  },
  {
    key: 'normaai-workflow-items',
    purpose: 'Attività della pagina di workflow.',
    duration: 'Chiusura della scheda.',
  },
  {
    key: 'normaai_demo_reports',
    purpose: 'Report creati nella demo con dati di esempio.',
    duration: 'Chiusura della scheda.',
  },
  {
    key: 'normaai_demo_clients',
    purpose: 'Clienti creati o modificati nella demo con dati di esempio.',
    duration: 'Chiusura della scheda.',
  },
  {
    key: 'normaai_demo_clients_deleted',
    purpose: 'Clienti rimossi nella demo con dati di esempio.',
    duration: 'Chiusura della scheda.',
  },
]

function StorageTable({ rows }: { rows: StorageRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-small">
        <thead>
          <tr className="border-b border-rule text-left text-ink-2">
            <th className="py-2 pr-4 font-semibold">Chiave</th>
            <th className="py-2 pr-4 font-semibold">Finalità</th>
            <th className="py-2 font-semibold">Durata</th>
          </tr>
        </thead>
        <tbody className="align-top">
          {rows.map((row) => (
            <tr key={row.key} className="border-b border-rule">
              <td className="py-2 pr-4 font-mono text-ink">{row.key}</td>
              <td className="py-2 pr-4">{row.purpose}</td>
              <td className="py-2">{row.duration}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function CookiePage() {
  return (
    <LegalLayout
      title="Cookie Policy"
      intro="Quali cookie e quali tecnologie di archiviazione locale usa NormaAI, ai sensi della Direttiva ePrivacy e del Provvedimento del Garante per la protezione dei dati personali n. 231/2021."
      lastUpdated="23 ottobre 2026"
    >
      <LegalSection title="1. Cosa copre questa pagina">
        <p>
          I cookie sono piccoli file di testo che i siti salvano sul dispositivo. Questa pagina
          copre anche le tecnologie analoghe del browser,{' '}
          <code className="font-mono">localStorage</code> e{' '}
          <code className="font-mono">sessionStorage</code>, che NormaAI usa per le stesse finalità
          tecniche.
        </p>
      </LegalSection>

      <LegalSection title="2. Cookie">
        <p>
          NormaAI <strong>non imposta cookie</strong>, né propri né di terze parti.
          L&apos;autenticazione e le preferenze usano l&apos;archiviazione locale del browser descritta
          qui sotto.
        </p>
      </LegalSection>

      <LegalSection title="3. Archiviazione locale del browser">
        <p>
          Tutte le chiavi sono di prima parte, scritte e lette solo da normaai.org, e servono al
          funzionamento del sito e dell&apos;applicazione. Nessuna viene usata per tracciare o
          profilare.
        </p>
        <p>
          Chiavi in <code className="font-mono">localStorage</code> (restano finché non le cancelli
          tu; le prime tre vengono cancellate dal logout):
        </p>
        <StorageTable rows={LOCAL_STORAGE} />
        <p>
          Chiavi in <code className="font-mono">sessionStorage</code> (cancellate dal browser alla
          chiusura della scheda):
        </p>
        <StorageTable rows={SESSION_STORAGE} />
      </LegalSection>

      <LegalSection title="4. Strumenti di terze parti">
        <p>
          Il sito carica <strong>Vercel Web Analytics</strong>, che non usa cookie né archiviazione
          locale e raccoglie statistiche di visita in forma aggregata, senza identificare il
          visitatore. Non ci sono altri script di terze parti: niente Google Analytics, Tag
          Manager, pixel pubblicitari o social plugin. I caratteri tipografici sono serviti dal
          nostro dominio.
        </p>
        <p>
          Se in futuro venissero introdotti strumenti che usano cookie o identificatori, questa
          pagina verrà aggiornata e il consenso verrà chiesto prima dell&apos;attivazione.
        </p>
      </LegalSection>

      <LegalSection title="5. Base giuridica e consenso">
        <p>
          L&apos;archiviazione strettamente tecnica è esente dal consenso preventivo ai sensi
          dell&apos;art. 122 del Codice privacy (D.Lgs. 196/2003) e delle Linee guida del Garante
          (Provv. n. 231/2021). Per questo NormaAI non mostra un banner con accetta e rifiuta:
          mostra un&apos;informativa con il rimando a questa pagina e il pulsante &quot;Ho capito&quot;.
        </p>
      </LegalSection>

      <LegalSection title="6. Come gestire l'archiviazione">
        <p>
          Puoi cancellare i dati dalle impostazioni del browser (dati dei siti). Il logout cancella
          i token e il segnale della demo. Se blocchi l&apos;archiviazione locale, l&apos;accesso
          all&apos;area riservata non funziona, perché i token di sessione sono conservati lì.
        </p>
      </LegalSection>

      <LegalSection title="7. Contatti">
        <p>
          Per qualsiasi richiesta sul trattamento dei dati scrivi a{' '}
          <a href="mailto:info@normaai.org">info@normaai.org</a>. Vedi anche la{' '}
          <a href="/privacy">Privacy Policy</a>.
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
