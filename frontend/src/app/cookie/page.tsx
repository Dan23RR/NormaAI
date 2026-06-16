import { LegalLayout, LegalSection } from '@/components/LegalLayout'

export const metadata = {
  title: 'Cookie Policy — NormaAI',
}

export default function CookiePage() {
  return (
    <LegalLayout
      title="Cookie Policy"
      intro="Quali cookie e tecnologie di archiviazione locale usa NormaAI, ai sensi della Direttiva ePrivacy e del Provvedimento del Garante per la protezione dei dati personali n. 231/2021."
      lastUpdated="Maggio 2026 · NormaAI v0.3"
    >
      <LegalSection title="1. Cosa sono i cookie">
        <p>
          I cookie sono piccoli file di testo che i siti visitati salvano sul dispositivo
          dell&apos;utente. Insieme ai cookie, questa policy copre anche tecnologie analoghe di
          archiviazione locale del browser (es. <code>localStorage</code>) utilizzate per finalità
          tecniche.
        </p>
      </LegalSection>

      <LegalSection title="2. Cookie utilizzati da NormaAI">
        <p>
          NormaAI utilizza <strong className="text-night">esclusivamente cookie e storage tecnici
          di prima parte</strong>, strettamente necessari all&apos;erogazione del servizio. Non sono
          presenti cookie di profilazione, pubblicitari né strumenti di analytics o tracciamento di
          terze parti.
        </p>
        <div className="overflow-x-auto">
          <table className="mt-2 w-full border-collapse text-xs">
            <thead>
              <tr className="border-b border-line text-left text-night">
                <th className="py-2 pr-4 font-semibold">Nome / chiave</th>
                <th className="py-2 pr-4 font-semibold">Tipo</th>
                <th className="py-2 pr-4 font-semibold">Finalità</th>
                <th className="py-2 font-semibold">Durata</th>
              </tr>
            </thead>
            <tbody className="align-top">
              <tr className="border-b border-line/60">
                <td className="py-2 pr-4 font-mono">access_token / refresh_token</td>
                <td className="py-2 pr-4">Tecnico (sessione)</td>
                <td className="py-2 pr-4">
                  Autenticazione dell&apos;utente alla dashboard e mantenimento della sessione.
                </td>
                <td className="py-2">Sessione / fino al logout</td>
              </tr>
              <tr className="border-b border-line/60">
                <td className="py-2 pr-4 font-mono">normaai.locale</td>
                <td className="py-2 pr-4">Tecnico (funzionale)</td>
                <td className="py-2 pr-4">Memorizza la lingua scelta (italiano / inglese).</td>
                <td className="py-2">Persistente (browser)</td>
              </tr>
              <tr className="border-b border-line/60">
                <td className="py-2 pr-4 font-mono">normaai.* (preferenze UI)</td>
                <td className="py-2 pr-4">Tecnico (funzionale)</td>
                <td className="py-2 pr-4">
                  Stato dell&apos;interfaccia (es. sidebar, preferenze alert, banner cookie).
                </td>
                <td className="py-2">Persistente (browser)</td>
              </tr>
            </tbody>
          </table>
        </div>
      </LegalSection>

      <LegalSection title="3. Base giuridica e consenso">
        <p>
          I cookie strettamente tecnici sono esenti dall&apos;obbligo di consenso preventivo ai
          sensi dell&apos;Art. 122 del Codice Privacy (D.Lgs. 196/2003) e delle Linee guida del
          Garante (Provv. n. 231/2021). Per questo motivo NormaAI non mostra un banner di opt-in con
          accettazione o rifiuto: visualizza una semplice informativa con rimando a questa pagina.
        </p>
      </LegalSection>

      <LegalSection title="4. Cookie di terze parti">
        <p>
          Allo stato attuale NormaAI <strong className="text-night">non installa alcun cookie di
          terze parti</strong> (nessun Google Analytics, Google Tag Manager, pixel pubblicitari o
          social plugin). Qualora in futuro venissero introdotti strumenti di misurazione o
          marketing, questa policy verrà aggiornata e verrà richiesto il consenso esplicito prima
          dell&apos;attivazione.
        </p>
      </LegalSection>

      <LegalSection title="5. Come gestire o disabilitare i cookie">
        <p>
          L&apos;utente può eliminare o bloccare cookie e archiviazione locale dalle impostazioni
          del proprio browser. La disabilitazione dei cookie tecnici di sessione impedisce
          l&apos;accesso all&apos;area riservata (dashboard), poiché necessari per mantenere
          l&apos;autenticazione.
        </p>
      </LegalSection>

      <LegalSection title="6. Contatti">
        <p>
          Per qualsiasi richiesta relativa al trattamento dei dati o ai cookie è possibile scrivere
          a{' '}
          <a
            href="mailto:privacy@normaai.org"
            className="text-clay transition hover:text-clay-deep"
          >
            privacy@normaai.org
          </a>
          . Si veda anche la{' '}
          <a href="/privacy" className="text-clay transition hover:text-clay-deep">
            Privacy Policy
          </a>
          .
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
