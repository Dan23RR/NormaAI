import { LegalLayout, LegalSection } from '@/components/LegalLayout'

export const metadata = {
  title: 'Sicurezza',
}

const REPO = 'https://github.com/Dan23RR/NormaAI'

/** Files of the public repository where a reader can check the claims above. */
function InCode({ paths }: { paths: string[] }) {
  return (
    <p className="text-small text-ink-3">
      Nel codice:{' '}
      {paths.map((path, i) => (
        <span key={path}>
          {i > 0 && ', '}
          <a href={`${REPO}/blob/main/${path}`} target="_blank" rel="noopener noreferrer">
            <code className="font-mono">{path}</code>
          </a>
        </span>
      ))}
      .
    </p>
  )
}

export default function SecurityPage() {
  return (
    <LegalLayout
      title="Sicurezza"
      intro="Le misure di sicurezza presenti nel codice di NormaAI e quelle che ancora mancano. Il codice è pubblico: ogni sezione indica i file da cui è presa, così chi deve valutarci può controllare invece di fidarsi."
      lastUpdated="23 ottobre 2026"
    >
      <LegalSection title="1. Dove girano il sito, l'API e i dati">
        <p>
          Il sito pubblico e l&apos;interfaccia dell&apos;applicazione sono ospitati su Vercel, nella
          regione fra1 (Francoforte). L&apos;API e i database (PostgreSQL per i dati, Qdrant per la
          ricerca, Redis per cache e sessioni) girano su un server Hetzner in Germania.
        </p>
        <p>
          In produzione l&apos;unico servizio esposto a internet è Caddy, che termina il TLS con
          certificati Let&apos;s Encrypt (porte 80 e 443) e inoltra le richieste all&apos;applicazione
          su una rete interna. L&apos;applicazione non ha porte pubbliche, gira in un container senza
          privilegi di root, con filesystem in sola lettura e senza capability Linux aggiuntive.
        </p>
        <InCode
          paths={[
            'frontend/vercel.json',
            'docker-compose.prod.yml',
            'infra/Caddyfile',
            'docker-compose.yml',
            'Dockerfile',
          ]}
        />
      </LegalSection>

      <LegalSection title="2. Il modello linguistico">
        <p>
          Le risposte sono scritte da un modello linguistico di terze parti. Per impostazione
          predefinita è Google Gemini (impostazione <code className="font-mono">llm_provider</code>{' '}
          uguale a <code className="font-mono">gemini</code>, modello della famiglia Gemini 2.5 Flash).
          Per generare una risposta, la domanda, il profilo aziendale eventualmente inserito e i
          passaggi normativi recuperati dal corpus vengono inviati al fornitore del modello, che li
          elabora sui propri sistemi.
        </p>
        <p>
          Il fornitore si può cambiare in configurazione: il codice supporta anche Anthropic e
          OpenRouter. Oggi non esiste una modalità in cui le risposte sono generate interamente sui
          nostri server.
        </p>
        <InCode paths={['src/config.py']} />
      </LegalSection>

      <LegalSection title="3. Accesso e sessioni">
        <ul>
          <li>
            Si entra con email e password. Le password sono conservate solo come hash bcrypt con
            salt individuale.
          </li>
          <li>
            Il controllo della password richiede lo stesso tempo anche quando l&apos;email non
            esiste, così né i tempi di risposta né i codici di errore rivelano quali account
            esistono.
          </li>
          <li>Dopo 5 tentativi falliti, l&apos;accesso a quell&apos;email è bloccato per 5 minuti.</li>
          <li>
            Le sessioni usano token JWT firmati con RS256: una chiave privata firma, una chiave
            pubblica verifica. In produzione l&apos;applicazione si rifiuta di partire senza chiavi
            RSA. Il token di accesso dura 60 minuti, il token di rinnovo 7 giorni.
          </li>
          <li>
            Ogni rinnovo invalida il token precedente. Se un token già usato viene ripresentato,
            l&apos;intera famiglia di token viene revocata e l&apos;utente deve rifare il login. Il
            logout revoca i token in uso.
          </li>
          <li>
            La lista dei token revocati è in Redis. In produzione, se Redis non risponde, i token
            vengono rifiutati invece che accettati.
          </li>
          <li>
            Tre ruoli: admin, member, viewer. Le chiamate all&apos;API sono limitate in frequenza per
            utente o, se anonime, per indirizzo IP.
          </li>
          <li>
            Nel browser i token sono conservati nel localStorage e cancellati al logout (vedi la{' '}
            <a href="/cookie">cookie policy</a>).
          </li>
        </ul>
        <p>Non ci sono autenticazione a due fattori né SSO: vedi la sezione 11.</p>
        <InCode
          paths={[
            'src/auth/security.py',
            'src/auth/router.py',
            'src/auth/brute_force.py',
            'src/api/rate_limit.py',
          ]}
        />
      </LegalSection>

      <LegalSection title="4. Separazione tra organizzazioni">
        <p>
          Ogni organizzazione vede solo i propri dati, e la separazione è applicata dal database,
          non solo dall&apos;applicazione.
        </p>
        <ul>
          <li>
            PostgreSQL ha policy di Row Level Security su utenti, clienti, conversazioni,
            valutazioni e avvisi: ogni riga è visibile solo nella sessione dell&apos;organizzazione a
            cui appartiene.
          </li>
          <li>
            L&apos;applicazione si collega con un ruolo dedicato non superuser (
            <code className="font-mono">normaai_app</code>), perché PostgreSQL ignora le policy per i
            superuser e per i proprietari delle tabelle. In produzione, se il ruolo connesso è
            superuser, l&apos;applicazione si rifiuta di partire.
          </li>
          <li>
            Il contesto dell&apos;organizzazione viene impostato a ogni transazione e azzerato quando
            la connessione torna nel pool: non può passare da una richiesta a quella successiva.
          </li>
          <li>
            La cache delle risposte usa chiavi che includono l&apos;organizzazione: una risposta
            calcolata per un cliente non viene mai servita a un altro.
          </li>
          <li>
            Nel motore di ricerca ogni frammento di documento caricato porta l&apos;identificativo
            dell&apos;organizzazione. Una ricerca restituisce i frammenti dell&apos;organizzazione più
            il corpus normativo condiviso; una ricerca senza organizzazione restituisce solo il
            corpus condiviso, mai i documenti di altri.
          </li>
          <li>
            Un test con due organizzazioni gira in CI su PostgreSQL con un ruolo non superuser e
            blocca la build se un&apos;organizzazione vede i dati dell&apos;altra.
          </li>
        </ul>
        <InCode
          paths={[
            'alembic/versions/002_enable_rls_policies.py',
            'scripts/setup_app_role.sql',
            'src/db/engine.py',
            'src/api/lifespan.py',
            'src/cache.py',
            'src/nlp/embedding/indexer.py',
            'tests/test_rls_pool_isolation.py',
          ]}
        />
      </LegalSection>

      <LegalSection title="5. Documenti caricati">
        <p>
          Un documento caricato (PDF, HTML o immagine, fino a 50 MB) viene scritto in un file
          temporaneo, elaborato e cancellato alla fine dell&apos;elaborazione, anche se questa
          fallisce. Resta il testo estratto, suddiviso in frammenti e indicizzato nel motore di
          ricerca con l&apos;identificativo dell&apos;organizzazione.
        </p>
        <p>
          L&apos;amministratore dell&apos;organizzazione può esportare in JSON tutti i dati
          dell&apos;organizzazione e cancellare in blocco clienti, conversazioni, valutazioni, avvisi
          e frammenti indicizzati. La cancellazione richiede una conferma esplicita ed è registrata
          nel registro degli eventi.
        </p>
        <InCode paths={['src/api/routers/data.py', 'src/api/routers/gdpr.py']} />
      </LegalSection>

      <LegalSection title="6. Intestazioni HTTP, CORS e indirizzi IP">
        <ul>
          <li>
            Il sito invia Content-Security-Policy, X-Content-Type-Options, X-Frame-Options (DENY),
            Referrer-Policy, Permissions-Policy e Strict-Transport-Security. L&apos;API invia le
            stesse intestazioni (HSTS in produzione) e non espone il nome del server.
          </li>
          <li>
            Il CORS accetta solo le origini elencate in configurazione. In produzione
            un&apos;origine jolly impedisce l&apos;avvio.
          </li>
          <li>
            L&apos;indirizzo IP del client, usato per i limiti di frequenza e per il registro degli
            eventi, è letto dalla posizione aggiunta dal nostro proxy e non dal primo valore di
            X-Forwarded-For, che chiunque può falsificare.
          </li>
        </ul>
        <InCode
          paths={[
            'frontend/src/middleware.ts',
            'frontend/next.config.js',
            'src/api/middleware.py',
            'src/config.py',
            'src/audit.py',
          ]}
        />
      </LegalSection>

      <LegalSection title="7. Link di download firmati">
        <p>
          Chi richiede il Codex riceve un link firmato con HMAC-SHA256 e valido 30 giorni. La firma
          è verificata con un confronto in tempo costante; un link scaduto o modificato viene
          rifiutato. Il modulo pubblico è limitato in frequenza per indirizzo IP.
        </p>
        <InCode paths={['src/api/routers/leads.py']} />
      </LegalSection>

      <LegalSection title="8. Registro degli eventi">
        <p>
          Accessi riusciti e falliti, logout, rinnovi e riusi di token, creazione e cancellazione
          di clienti e conversazioni, domande, caricamenti di documenti, esportazioni e
          cancellazioni sono registrati come eventi strutturati con utente, organizzazione,
          indirizzo IP, data e ora ed esito.
        </p>
        <p>
          Oggi questi eventi finiscono nei log dell&apos;applicazione sul server. Non esistono ancora
          un archivio separato a lungo termine né un&apos;esportazione pronta per i revisori: la
          conservazione è quella dei log del server.
        </p>
        <InCode paths={['src/audit.py']} />
      </LegalSection>

      <LegalSection title="9. Backup">
        <p>
          Uno script avviato da cron ogni notte alle 02:00 esegue{' '}
          <code className="font-mono">pg_dump</code> del database PostgreSQL in formato compresso,
          verifica che l&apos;archivio sia leggibile con{' '}
          <code className="font-mono">pg_restore --list</code> e conserva le copie per 30 giorni nella
          cartella <code className="font-mono">backups/</code> dello stesso server.
        </p>
        <p>
          Lo script non cifra il file e non lo copia su un altro sistema: la copia settimanale su
          uno storage esterno è una procedura manuale documentata, non automatica. Qdrant e Redis
          non vengono salvati: l&apos;indice si ricostruisce con una nuova indicizzazione, la cache è
          effimera per costruzione. La procedura di ripristino è documentata nel repository.
        </p>
        <InCode paths={['scripts/backup_postgres.sh', 'docs/BACKUP_STRATEGY.md']} />
      </LegalSection>

      <LegalSection title="10. Sviluppo e catena di fornitura">
        <ul>
          <li>
            Il codice è pubblico su{' '}
            <a href={REPO} target="_blank" rel="noopener noreferrer">
              GitHub
            </a>{' '}
            con licenza MIT.
          </li>
          <li>
            A ogni push e pull request la CI esegue ruff (lint e formato), mypy (bloccante sui
            moduli di autenticazione, database e audit), i test del backend su PostgreSQL, Qdrant e
            Redis reali, type-check, test e build del frontend, la build dell&apos;immagine Docker
            con scansione Trivy, Gitleaks sull&apos;intera cronologia git, Bandit e la generazione di
            una SBOM CycloneDX.
          </li>
          <li>
            CodeQL analizza Python e JavaScript/TypeScript con le query security-extended a ogni
            push sul ramo principale e ogni settimana.
          </li>
          <li>
            A ogni release l&apos;immagine è bloccata se Trivy trova vulnerabilità critiche o alte, e
            la SBOM è allegata alla release. Dependabot propone gli aggiornamenti delle dipendenze.
          </li>
          <li>
            I file <code className="font-mono">.env</code> e le chiavi{' '}
            <code className="font-mono">.pem</code> sono esclusi dal repository; la CI fallisce se
            trova chiavi API o chiavi private nei file tracciati.
          </li>
        </ul>
        <InCode
          paths={[
            '.github/workflows/ci.yml',
            '.github/workflows/codeql.yml',
            '.github/workflows/release.yml',
            '.github/dependabot.yml',
            'LICENSE',
          ]}
        />
      </LegalSection>

      <LegalSection title="11. Cosa manca oggi">
        <ul>
          <li>
            Nessun SSO (SAML o OpenID Connect) e nessuna autenticazione a due fattori: si entra
            solo con email e password.
          </li>
          <li>
            Nessuna certificazione SOC 2 o ISO 27001 e nessun penetration test formale di terze
            parti. Le scansioni automatiche in CI non lo sostituiscono.
          </li>
          <li>
            Nessuna cifratura dei dati a riposo gestita dall&apos;applicazione: la protezione dei dati
            sul disco è quella del server.
          </li>
          <li>
            Nessun archivio a lungo termine del registro degli eventi e nessuna copia di backup
            automatica fuori dal server.
          </li>
          <li>
            Il filtro contro le prompt injection registra i tentativi ma non blocca l&apos;input. La
            difesa reale è strutturale: il testo dell&apos;utente non entra mai nel prompt di sistema
            e le citazioni vengono controllate contro i passaggi recuperati.
          </li>
          <li>Nessun programma di bug bounty.</li>
        </ul>
        <InCode paths={['src/agents/sanitization.py', 'SECURITY.md']} />
      </LegalSection>

      <LegalSection title="12. Segnalare una vulnerabilità">
        <p>
          Scrivi a{' '}
          <a href="mailto:info@normaai.org?subject=%5BSECURITY%5D%20NormaAI">info@normaai.org</a>{' '}
          con oggetto <code className="font-mono">[SECURITY] NormaAI</code>, indicando come riprodurre
          il problema e l&apos;impatto. Non aprire una issue pubblica su GitHub.
        </p>
        <ul>
          <li>Conferma di ricezione entro 48 ore.</li>
          <li>Valutazione della gravità entro 5 giorni lavorativi.</li>
          <li>Correzione o mitigazione delle segnalazioni critiche e alte entro 30 giorni.</li>
          <li>Nessuna ricompensa economica; riconoscimento nelle note di rilascio, se gradito.</li>
        </ul>
        <p>
          Ricevono correzioni di sicurezza solo il ramo principale e l&apos;ultima release pubblicata.
        </p>
        <p>
          Per questionari di sicurezza o per il modello di accordo sul trattamento dei dati (art.
          28 GDPR, nella cartella <code className="font-mono">docs/legal/</code> del repository) scrivi
          allo stesso indirizzo.
        </p>
        <InCode paths={['SECURITY.md', 'docs/legal/DPA_template_clienti.md']} />
      </LegalSection>
    </LegalLayout>
  )
}
