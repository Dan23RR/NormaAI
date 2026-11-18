# Accordo sul Trattamento dei Dati Personali (Data Processing Agreement)

> **Modello da completare e da far rivedere a un avvocato prima dell'uso.** Non è un contratto pronto da firmare. I campi tra parentesi quadre `[...]` vanno compilati e le note `[NOTA: ...]` vanno risolte e tolte; l'intero testo va verificato da un legale rispetto al contratto di servizio e alla situazione del Fornitore al momento della firma. Le misure di sicurezza e i sub-responsabili elencati qui sono quelli che il codice e la configurazione del repository mostrano alla data del modello: vanno confermati alla firma.

**Allegato al contratto di servizio NormaAI, ai sensi dell'art. 28 del Regolamento (UE) 2016/679 (GDPR)**

> Versione del modello: 18 novembre 2026.
> Le clausole obbligatorie ex art. 28, par. 3, GDPR sono predisposte e non vanno modificate senza confronto legale.

---

## Parti

| Ruolo | Soggetto |
|---|---|
| **Titolare del trattamento** (di seguito "Cliente" o "Titolare") | `[Ragione sociale del Cliente]`, P.IVA `[...]`, sede legale `[...]`, in persona del legale rappresentante `[...]`; DPO, se nominato: `[...]` |
| **Responsabile del trattamento** (di seguito "Fornitore") | Il fornitore del servizio NormaAI, come identificato nel contratto di servizio: `[nome o ragione sociale, P.IVA se presente, sede o indirizzo]`. Contatto per la protezione dei dati: info@normaai.org |

Le Parti, premesso che il Cliente utilizza il servizio NormaAI (di seguito il "Servizio") e che nell'erogazione del Servizio il Fornitore tratta dati personali per conto del Cliente, concordano quanto segue ai sensi dell'art. 28 GDPR.

---

## 1. Oggetto, durata, natura e finalità del trattamento

**1.1 Oggetto.** Il trattamento ha ad oggetto i dati personali contenuti nei dati che il Cliente e i suoi utenti inseriscono nel Servizio: account degli utenti, profili delle aziende seguite, domande e risposte, documenti sottoposti al controllo dei riferimenti di legge, avvisi, metadati di utilizzo.

**1.2 Natura e finalità.** Il trattamento è svolto esclusivamente per erogare il Servizio:
- controllo dei riferimenti di legge nei documenti: confronto deterministico con il testo ufficiale (EUR-Lex, Normattiva), senza modelli linguistici generativi;
- sorveglianza delle disposizioni citate nei documenti e avvisi quando cambiano;
- risposte alle domande, scritte da un modello linguistico di un fornitore esterno (art. 5) a partire dai testi normativi recuperati;
- gestione degli account, delle aziende seguite e dei report.

Il Fornitore non tratta i dati per finalità proprie diverse dall'erogazione del Servizio.

**1.3 Durata.** Il trattamento ha la stessa durata del contratto di servizio sottostante. Alla cessazione si applica l'art. 8 del presente Accordo (cancellazione o restituzione).

**1.4 Base giuridica del Titolare.** Il Cliente, in qualità di Titolare, è responsabile dell'individuazione della base giuridica del trattamento ex art. 6 GDPR e garantisce di disporre di una valida base per il conferimento dei dati al Fornitore.

---

## 2. Categorie di interessati e tipologie di dati

**2.1 Categorie di interessati.** A titolo indicativo: utenti del Cliente (dipendenti, collaboratori), referenti delle aziende seguite dal Cliente e altre persone i cui dati personali siano contenuti nei documenti e nelle domande che il Cliente sottopone al Servizio.

**2.2 Tipologie di dati personali.**
- Account degli utenti: email, nome, ruolo, organizzazione; la password è conservata solo come hash bcrypt.
- Profili delle aziende seguite (settore, dimensione, fatturato, giurisdizioni), nella misura in cui contengano dati riferibili a persone fisiche.
- Domande, risposte e cronologia delle conversazioni.
- Documenti sottoposti al controllo dei riferimenti di legge (il cui contenuto è determinato unilateralmente dal Cliente): il file è letto in memoria e non viene conservato. Restano il nome del file, la sua impronta SHA-256, le date e, per ogni riferimento trovato, al massimo 160 caratteri del documento intorno al riferimento, le citazioni e l'esito.
- `[NOTA: se alla firma è ancora attivo il caricamento di documenti per le risposte (POST /api/v1/documents/upload), il testo estratto da quei documenti resta nell'indice di ricerca, separato per organizzazione, fino alla cancellazione dei dati dell'organizzazione, e i passaggi recuperati possono essere inviati al fornitore del modello linguistico insieme alla domanda: aggiungere questa voce e adeguare l'art. 5, oppure confermare che la funzione è disattivata.]`
- Metadati di utilizzo: registro degli eventi di sicurezza (utente, organizzazione, indirizzo IP, data e ora, esito).

**2.3 Categorie particolari di dati (artt. 9 e 10 GDPR).** Il Servizio non è progettato per il trattamento di categorie particolari di dati. Il Cliente si impegna a non caricare dati ex artt. 9 e 10 GDPR salvo preventivo accordo scritto e adozione di misure aggiuntive.

---

## 3. Obblighi del Responsabile

Ai sensi dell'art. 28, par. 3, GDPR, il Fornitore si impegna a:

1. **trattare i dati solo su istruzione documentata** del Titolare (il presente Accordo e il contratto di servizio costituiscono le istruzioni iniziali), anche per i trasferimenti verso Paesi terzi, salvo obblighi di legge dell'Unione o dello Stato membro (nel qual caso ne informa il Titolare prima del trattamento, salvo divieto di legge);
2. **garantire la riservatezza**, assicurando che le persone autorizzate al trattamento si siano impegnate alla riservatezza o vi siano soggette per legge;
3. **adottare misure tecniche e organizzative adeguate** ex art. 32 GDPR (vedi art. 4);
4. rispettare le **condizioni per il ricorso a sub-responsabili** (vedi art. 5);
5. **assistere il Titolare** con misure tecniche e organizzative adeguate per dar seguito alle richieste di esercizio dei diritti degli interessati (vedi art. 6);
6. **assistere il Titolare** nel garantire il rispetto degli obblighi ex artt. 32-36 GDPR (sicurezza, notifica delle violazioni, valutazione d'impatto, consultazione preventiva), tenuto conto della natura del trattamento e delle informazioni disponibili;
7. su scelta del Titolare, **cancellare o restituire** tutti i dati personali al termine del Servizio (vedi art. 8);
8. mettere a disposizione del Titolare **tutte le informazioni necessarie** a dimostrare il rispetto degli obblighi e consentire e contribuire alle **attività di audit** (vedi art. 9);
9. **informare immediatamente** il Titolare qualora, a suo parere, un'istruzione violi il GDPR o altre disposizioni in materia di protezione dei dati.

---

## 4. Misure di sicurezza (art. 32 GDPR)

**4.1 Misure adottate.** Il Fornitore adotta le misure seguenti, presenti nel codice e nella configurazione del Servizio. Il codice è pubblico (https://github.com/Dan23RR/NormaAI): tra parentesi i file in cui ciascuna misura si può verificare.

*Riservatezza in transito*
- Connessioni cifrate con TLS: il sito e l'interfaccia su Vercel in HTTPS; l'API dietro Caddy, che ottiene i certificati da Let's Encrypt e invia l'intestazione Strict-Transport-Security (`infra/Caddyfile`, `docker-compose.prod.yml`).

*Separazione tra clienti del Servizio*
- Row Level Security di PostgreSQL sulle tabelle dei dati delle organizzazioni (aziende seguite, conversazioni, valutazioni, avvisi, inviti, controlli dei documenti e disposizioni sorvegliate). Il contesto dell'organizzazione è impostato a ogni transazione e azzerato quando la connessione torna nel pool (`src/db/engine.py`, `alembic/versions/`).
- L'applicazione si collega al database con un ruolo non superuser (`normaai_app`); in produzione si rifiuta di partire se il ruolo è superuser o può aggirare la Row Level Security (`src/api/lifespan.py`, `scripts/setup_app_role.sql`, `docker-compose.rls.yml`).
- Le tabelle degli utenti e delle organizzazioni non hanno policy di Row Level Security: per esse la separazione è applicata dalle query dell'applicazione.
- Chiavi della cache e filtri dell'indice di ricerca per organizzazione; un test con due organizzazioni e un ruolo non superuser gira in CI e blocca la build se un'organizzazione vede i dati dell'altra (`src/cache.py`, `src/nlp/embedding/indexer.py`, `tests/test_rls_pool_isolation.py`).

*Autenticazione e sessioni*
- Password conservate solo come hash bcrypt; il controllo della password richiede lo stesso tempo anche per un'email che non esiste (`src/auth/security.py`, `src/auth/router.py`).
- Blocco dell'accesso per 5 minuti dopo 5 tentativi falliti; limiti di frequenza per indirizzo IP su registrazione, accesso e rinnovo della sessione (`src/auth/brute_force.py`, `src/api/rate_limit.py`).
- Token di sessione JWT firmati con RS256: in produzione l'applicazione non parte senza chiavi RSA. Il token di accesso dura 60 minuti, quello di rinnovo 7 giorni; ogni rinnovo invalida il token precedente e il riuso di un token già usato revoca l'intera famiglia di token. L'elenco dei token revocati è in Redis e, in produzione, se Redis non risponde i token sono rifiutati (`src/auth/security.py`, `src/auth/router.py`).
- Registrazione su invito: codici monouso, con scadenza, conservati solo come hash SHA-256 (`src/auth/invites.py`).

*Ambiente di esecuzione*
- In produzione l'unico servizio esposto a internet è Caddy (porte 80 e 443); l'applicazione non ha porte pubbliche (`docker-compose.prod.yml`).
- Il container dell'applicazione gira con un utente senza privilegi di root, con il filesystem in sola lettura, con tutte le capability Linux tolte salvo `NET_BIND_SERVICE` e con l'opzione `no-new-privileges` (`Dockerfile`, `docker-compose.yml`).
- I file con le chiavi e le password (`.env`, chiavi `.pem`) sono esclusi dal repository; la CI cerca chiavi e segreti nell'intera cronologia del codice.

*Documenti controllati*
- Il file sottoposto al controllo dei riferimenti è letto in memoria: non è scritto su disco, non è conservato e il suo testo non finisce nei log (`SECURITY.md`, sezione "What the document check stores").

*Registro degli eventi*
- Accessi riusciti e falliti, rinnovi e riusi dei token, creazioni e cancellazioni, esportazioni sono registrati come eventi strutturati con utente, organizzazione, indirizzo IP, data, ora ed esito (`src/audit.py`). Sono righe dei log dell'applicazione, senza un archivio separato a lungo termine.

*Backup e ripristino*
- Ogni notte uno script copia il database (`pg_dump`, verificato con `pg_restore --list`) e conserva le copie per 30 giorni. Quando è configurato un archivio restic, lo script invia fuori dal server il database, l'indice di ricerca e la configurazione, cifrati sul server da restic prima dell'invio (`scripts/backup.sh`, `docs/BACKUP_STRATEGY.md`).
- `[NOTA: alla firma confermare che l'archivio restic è configurato e che un ripristino è stato provato. Alla data del modello nessun backup è stato inviato a un archivio reale e nessun ripristino è stato fatto; senza archivio restic resta solo una copia non cifrata sul disco del server.]`

*Assistenza al Titolare*
- L'amministratore dell'organizzazione può esportare in JSON i dati dell'organizzazione e cancellarli dall'applicazione (`src/api/routers/gdpr.py`).

**4.2 Misure non presenti.** Perché il Titolare non faccia affidamento su misure che non esistono, il Fornitore dichiara che il Servizio oggi non ha: autenticazione a due fattori né accesso tramite SSO (SAML o OpenID Connect); cifratura dei dati a riposo gestita dall'applicazione (la protezione dei dati sul disco è quella del server); certificazioni (SOC 2, ISO 27001) né penetration test di terzi; un archivio a lungo termine del registro degli eventi.

**4.3 Aggiornamenti.** Le misure, e quelle che mancano, sono descritte anche nella pagina pubblica https://normaai.org/security. Possono essere aggiornate purché il livello di protezione non sia ridotto.

---

## 5. Sub-responsabili del trattamento (art. 28, par. 2 e 4)

**5.1 Autorizzazione generale.** Il Titolare autorizza il ricorso ai sub-responsabili elencati di seguito. Il Fornitore stipula con ciascun sub-responsabile un contratto che impone obblighi di protezione dei dati equivalenti a quelli del presente Accordo e resta pienamente responsabile verso il Titolare per l'operato dei sub-responsabili.

**5.2 Elenco dei sub-responsabili autorizzati:**

| Sub-responsabile | Trattamento | Luogo e trasferimento extra-UE | Garanzie |
|---|---|---|---|
| **Hetzner Online GmbH** (Germania) | Server dell'API, del database (PostgreSQL), dell'indice di ricerca (Qdrant) e della cache (Redis); copie di backup sul disco del server | Germania (UE); nessun trasferimento extra-UE | Trattamento nello SEE |
| **Anthropic PBC** (USA), modello linguistico Claude | Scrittura delle risposte alle domande: riceve la domanda, il profilo aziendale eventualmente inserito e i passaggi normativi recuperati. Non riceve i documenti sottoposti al controllo dei riferimenti | USA; trasferimento extra-UE | Clausole contrattuali standard previste dall'accordo sul trattamento del fornitore `[NOTA: verificare alla firma l'accordo sul trattamento, i termini sull'uso dei dati inviati all'API e l'eventuale adesione all'EU-US Data Privacy Framework]` |
| **Vercel Inc.** (USA) | Hosting del sito e dell'interfaccia dell'applicazione, con le funzioni lato server nella regione di Francoforte: riceve le richieste delle pagine (indirizzo IP, intestazioni della richiesta). Le chiamate all'API vanno dal browser al server del Fornitore senza passare da Vercel | Società statunitense; possibile trasferimento extra-UE | Clausole contrattuali standard previste dall'accordo sul trattamento del fornitore `[NOTA: da verificare alla firma]` |
| **Resend, Inc.** (USA) | Invio delle email del Servizio: conferma dell'indirizzo email, riepilogo degli avvisi sulle norme citate | USA; trasferimento extra-UE | Clausole contrattuali standard previste dall'accordo sul trattamento del fornitore `[NOTA: da verificare alla firma]` |
| **Cloudflare, Inc.** (USA) | DNS del dominio normaai.org e instradamento della posta in arrivo a info@normaai.org (per esempio le richieste di assistenza) | USA; possibile trasferimento extra-UE | Clausole contrattuali standard previste dall'accordo sul trattamento del fornitore `[NOTA: da verificare alla firma]` |
| `[Fornitore dell'archivio dei backup, se configurato]` | Conservazione delle copie di backup cifrate sul server da restic prima dell'invio: il fornitore riceve solo dati cifrati | `[...]` | `[...]` |

Il codice del Servizio permette di configurare, al posto di Anthropic, un altro fornitore del modello linguistico: Google (API Gemini, USA), Mistral AI (endpoint dell'Unione europea) o OpenRouter (USA). Il Fornitore non ne usa uno senza averlo prima comunicato al Titolare secondo l'art. 5.3.

**5.3 Modifiche.** Il Fornitore informa il Titolare di eventuali modifiche relative all'aggiunta o alla sostituzione di sub-responsabili con **almeno 30 giorni di preavviso**, dando al Titolare la possibilità di opporsi per motivi ragionevoli e documentati. In caso di opposizione non risolvibile, ciascuna Parte può recedere dalla parte di Servizio interessata.

---

## 6. Assistenza per i diritti degli interessati (artt. 12-23 GDPR)

Il Fornitore assiste il Titolare, con misure tecniche e organizzative adeguate e nella misura del possibile, a dar seguito alle richieste degli interessati relative a: accesso, rettifica, cancellazione, limitazione, portabilità e opposizione. Qualora una richiesta dell'interessato pervenga direttamente al Fornitore, questi non vi dà autonomamente seguito ma la trasmette senza ingiustificato ritardo al Titolare, indirizzando l'interessato al Titolare medesimo.

---

## 7. Violazioni dei dati personali: notifica (artt. 33-34 GDPR)

**7.1 Notifica al Titolare.** Il Fornitore notifica al Titolare ogni violazione di dati personali **senza ingiustificato ritardo e comunque entro 48 ore** dal momento in cui ne è venuto a conoscenza, così da consentire al Titolare di adempiere ai propri obblighi (di norma la notifica all'Autorità di controllo entro 72 ore ex art. 33).

**7.2 Contenuto minimo della notifica** (ex art. 33, par. 3), nella misura delle informazioni disponibili:
- natura della violazione, categorie e numero approssimativo di interessati e di registrazioni coinvolti;
- nome e contatti del punto di riferimento del Fornitore (info@normaai.org) per ulteriori informazioni;
- probabili conseguenze della violazione;
- misure adottate o proposte per porvi rimedio e per attenuarne i possibili effetti negativi.

**7.3 Cooperazione.** Il Fornitore coopera con il Titolare e adotta le misure correttive ragionevoli; ove non tutte le informazioni siano disponibili al momento della prima notifica, le fornisce successivamente in fasi senza ulteriore ingiustificato ritardo. Il Fornitore non effettua comunicazioni a terzi (interessati, Autorità, media) in merito alla violazione senza previo coordinamento con il Titolare, salvo obblighi di legge.

---

## 8. Cancellazione o restituzione dei dati a fine contratto

Alla cessazione del Servizio, a scelta del Titolare, il Fornitore **cancella** oppure **restituisce** tutti i dati personali trattati per conto del Titolare (la restituzione avviene con l'esportazione in JSON dei dati dell'organizzazione) e cancella le copie esistenti, salvo che il diritto dell'Unione o dello Stato membro richieda la conservazione. La cancellazione è completata **entro 90 giorni** dal termine del contratto; un dato cancellato può restare nelle copie di backup fino a 30 giorni, il periodo per cui sono conservate. Su richiesta, il Fornitore fornisce attestazione scritta dell'avvenuta cancellazione.

---

## 9. Audit e ispezioni (art. 28, par. 3, lett. h)

Il Fornitore mette a disposizione del Titolare le informazioni necessarie a dimostrare la conformità agli obblighi del presente Accordo e consente e contribuisce ad audit, anche tramite ispezioni, condotti dal Titolare o da un revisore da questi incaricato. Gli audit sono concordati con ragionevole preavviso (di norma **almeno 14 giorni**), svolti in orari lavorativi, in modo da non compromettere la sicurezza degli altri clienti e con costi a carico del Titolare salvo che l'audit riveli una non conformità sostanziale. Il Fornitore oggi non dispone di certificazioni (SOC 2, ISO 27001) né di report di audit di terzi; il codice del Servizio è pubblico e il Titolare può esaminarlo.

---

## 10. Disposizioni finali

**10.1 Gerarchia.** In caso di conflitto tra il presente Accordo e il contratto di servizio relativamente alla protezione dei dati, prevale il presente Accordo. In caso di conflitto con il GDPR, prevale il GDPR.

**10.2 Legge applicabile e foro.** Il presente Accordo è regolato dalla legge italiana; per quanto non previsto si rinvia al GDPR e alla normativa nazionale applicabile. Foro competente: `[da definire nel contratto di servizio]`.

**10.3 Modifiche.** Eventuali modifiche sono concordate per iscritto tra le Parti.

---

### Firme

| Titolare (Cliente) | Responsabile (il Fornitore) |
|---|---|
| Nome: `[...]` | Nome: `[...]` |
| Ruolo: `[...]` | Ruolo: `[...]` |
| Data: `[...]` | Data: `[...]` |
| Firma: ____________________ | Firma: ____________________ |

---

*Modello di accordo, da completare e da far rivedere a un avvocato prima della firma. Riferimenti incrociati: Privacy Policy (https://normaai.org/privacy), Termini di Servizio (https://normaai.org/terms), pagina Sicurezza (https://normaai.org/security).*
