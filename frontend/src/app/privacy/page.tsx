import { LegalLayout, LegalSection } from '@/components/LegalLayout'

export const metadata = {
  title: 'Privacy Policy',
}

export default function PrivacyPage() {
  return (
    <LegalLayout
      title="Privacy Policy"
      intro="Come NormaAI tratta i dati personali di chi usa l'applicazione, di chi visita il sito e di chi ci scrive, ai sensi del Regolamento (UE) 2016/679 (GDPR)."
      lastUpdated="23 ottobre 2026"
    >
      <LegalSection title="1. Titolare e Responsabile del trattamento">
        <p>
          NormaAI è un progetto di Daniel Culotta, persona fisica, Inverigo (CO), Italia, non
          ancora costituito in società. Per ogni richiesta sui dati personali scrivi a{' '}
          <a href="mailto:info@normaai.org">info@normaai.org</a>.
        </p>
        <p>
          Per i dati che un&apos;organizzazione inserisce nell&apos;applicazione (utenti, aziende
          analizzate, documenti, conversazioni) l&apos;organizzazione è Titolare del trattamento e
          Daniel Culotta è Responsabile ai sensi dell&apos;art. 28 GDPR. Un modello di accordo sul
          trattamento è pubblicato nel repository del codice (cartella{' '}
          <code className="font-mono">docs/legal/</code>) e si può richiedere allo stesso indirizzo.
        </p>
        <p>
          Per i dati di chi visita il sito, richiede il Codex o scrive via email, Titolare è Daniel
          Culotta.
        </p>
      </LegalSection>

      <LegalSection title="2. Dati trattati">
        <p>Nell&apos;applicazione, per gli utenti registrati:</p>
        <ul>
          <li>
            Account: email, nome, password (conservata solo come hash bcrypt), ruolo,
            organizzazione di appartenenza, stato attivo, data di creazione.
          </li>
          <li>Organizzazione: nome, identificativo, piano.</li>
          <li>
            Clienti, cioè le aziende analizzate: nome, settore, numero di dipendenti, fatturato,
            giurisdizioni, normative applicabili.
          </li>
          <li>
            Conversazioni: domande e risposte con i relativi metadati (per esempio le fonti
            citate), collegate all&apos;utente e, se indicato, al cliente.
          </li>
          <li>
            Documenti caricati: il file viene elaborato e cancellato; resta il testo estratto, in
            frammenti indicizzati con l&apos;identificativo dell&apos;organizzazione.
          </li>
          <li>Valutazioni (gap analysis) e avvisi generati per ciascun cliente.</li>
          <li>
            Registro degli eventi: azione, esito, utente, organizzazione, indirizzo IP, data e ora.
          </li>
          <li>
            Il profilo aziendale compilato nei moduli è conservato nel browser (sessionStorage) e
            inviato all&apos;API insieme alla domanda.
          </li>
        </ul>
        <p>Sul sito pubblico:</p>
        <ul>
          <li>
            Richiesta del Codex o di una demo: email, nome dell&apos;organizzazione, ruolo e modulo di
            provenienza. Quando la richiesta passa dall&apos;API, vengono salvati anche indirizzo IP,
            user agent e pagina di provenienza (per limitare lo spam), oltre alla data e al numero
            di download. Quando passa dalla funzione serverless su Vercel, i dati sono scritti nei
            log della funzione e inviati via email a info@normaai.org.
          </li>
          <li>Email: i dati contenuti nei messaggi inviati a info@normaai.org.</li>
          <li>
            Statistiche di visita: Vercel Web Analytics, senza cookie e senza identificare il
            visitatore.
          </li>
        </ul>
      </LegalSection>

      <LegalSection title="3. Base giuridica e finalità">
        <ul>
          <li>
            Erogazione del servizio e gestione dell&apos;account: esecuzione del contratto (art.
            6(1)(b) GDPR).
          </li>
          <li>
            Sicurezza del servizio (registro degli eventi, blocco dei tentativi di accesso ripetuti,
            limiti di frequenza, controllo dello spam): legittimo interesse (art. 6(1)(f) GDPR).
          </li>
          <li>
            Invio del Codex e ricontatto sullo stesso tema a chi lo ha richiesto: legittimo
            interesse (art. 6(1)(f) GDPR). Puoi opporti in qualsiasi momento rispondendo
            all&apos;email ricevuta o scrivendo a info@normaai.org.
          </li>
          <li>Risposta a chi ci scrive: legittimo interesse o misure precontrattuali.</li>
        </ul>
        <p>
          I dati non sono venduti né usati per profilazione pubblicitaria. Sono condivisi solo con
          i fornitori elencati nella sezione 4, per erogare il servizio.
        </p>
      </LegalSection>

      <LegalSection title="4. Sub-responsabili e fornitori">
        <ul>
          <li>
            <strong>Hetzner Online GmbH</strong> (Germania): server su cui girano l&apos;API e i
            database. I dati dell&apos;applicazione restano nell&apos;Unione europea.
          </li>
          <li>
            <strong>Vercel Inc.</strong> (USA): hosting del sito e dell&apos;interfaccia, nella
            regione di Francoforte, e funzione serverless che riceve le richieste del Codex.
            Statistiche di visita senza cookie.
          </li>
          <li>
            <strong>Google LLC</strong> (API Gemini, USA): il modello linguistico che genera le
            risposte. Riceve la domanda, il profilo aziendale eventualmente inserito e i passaggi
            normativi recuperati. È il fornitore predefinito; il codice permette di configurare in
            alternativa Anthropic o OpenRouter.
          </li>
          <li>
            <strong>Resend, Inc.</strong> (USA): invio delle email transazionali (consegna del Codex,
            notifica delle nuove richieste).
          </li>
          <li>
            <strong>Cloudflare, Inc.</strong>: solo gestione DNS del dominio normaai.org, senza proxy
            del traffico. Tratta le interrogazioni DNS, non i contenuti.
          </li>
        </ul>
        <p>
          Per i fornitori con sede negli Stati Uniti i trasferimenti si basano sulle clausole
          contrattuali standard previste dai loro accordi sul trattamento dei dati.
        </p>
      </LegalSection>

      <LegalSection title="5. Conservazione">
        <ul>
          <li>
            Dati dell&apos;applicazione: per tutta la durata del rapporto. Non esiste una
            cancellazione automatica a scadenza. L&apos;amministratore dell&apos;organizzazione può in
            qualsiasi momento esportare i dati e cancellare clienti, conversazioni, valutazioni,
            avvisi e frammenti indicizzati dall&apos;applicazione; ogni utente può cancellare le
            proprie conversazioni. Per chiudere gli account e l&apos;organizzazione scrivi a
            info@normaai.org.
          </li>
          <li>
            Copie di backup: il database è copiato ogni notte e le copie sono conservate 30 giorni
            sul server. Un dato cancellato può restare in una copia di backup fino a 30 giorni.
          </li>
          <li>
            Richieste del Codex: conservate nel database finché non ne viene chiesta la
            cancellazione. Il link di download scade dopo 30 giorni.
          </li>
          <li>Registro degli eventi: nei log del server, con la loro rotazione.</li>
          <li>
            Dati nel browser: vedi la <a href="/cookie">cookie policy</a>.
          </li>
        </ul>
      </LegalSection>

      <LegalSection title="6. Diritti dell'interessato">
        <p>
          Puoi chiedere accesso, rettifica, cancellazione, limitazione, portabilità e opposizione
          scrivendo a <a href="mailto:info@normaai.org">info@normaai.org</a>. Puoi anche proporre
          reclamo al Garante per la protezione dei dati personali.
        </p>
        <p>
          Nell&apos;applicazione, senza scriverci: l&apos;amministratore può esportare in formato JSON
          tutti i dati dell&apos;organizzazione e cancellarne i contenuti; ogni utente può cancellare
          le proprie conversazioni.
        </p>
        <p>
          Se i tuoi dati sono stati inseriti da un&apos;organizzazione che usa NormaAI (per esempio
          come azienda cliente analizzata), la richiesta va rivolta a quell&apos;organizzazione, che
          ne è Titolare; se arriva a noi, la inoltriamo.
        </p>
      </LegalSection>

      <LegalSection title="7. Trasparenza AI (art. 50 AI Act)">
        <p>
          NormaAI usa un modello linguistico generativo (Google Gemini per impostazione
          predefinita) per scrivere le risposte a partire dai passaggi normativi recuperati dal
          corpus, costruito da EUR-Lex e Normattiva (CSRD, CSDDD, AI Act, DORA, NIS2, Tassonomia
          UE, GDPR, CRA). Tutti gli output sono generati da un sistema di intelligenza artificiale,
          possono contenere errori e richiedono la verifica di un professionista. L&apos;avviso
          compare nell&apos;applicazione, nella pagina Chiedi e nei report.
        </p>
        <p>
          NormaAI non prende decisioni automatizzate con effetti giuridici sulle persone: produce
          analisi che un professionista valuta.
        </p>
      </LegalSection>

      <LegalSection title="8. Sicurezza">
        <p>
          Le misure di sicurezza presenti nel codice, e quelle che mancano ancora, sono descritte
          nella pagina <a href="/security">Sicurezza</a>.
        </p>
      </LegalSection>

      <LegalSection title="9. Modifiche">
        <p>
          Le modifiche a questa informativa sono pubblicate su questa pagina con la nuova data di
          aggiornamento.
        </p>
      </LegalSection>
    </LegalLayout>
  )
}
