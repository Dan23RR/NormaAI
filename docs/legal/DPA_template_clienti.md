# Accordo sul Trattamento dei Dati Personali (Data Processing Agreement)

**Allegato al contratto di servizio NormaAI — ai sensi dell'Art. 28 del Regolamento (UE) 2016/679 (GDPR)**

> Versione template: Marzo 2026 · NormaAI v0.3
> Questo documento è un modello (template) da allegare alla proposta di pilot / al contratto di servizio. I campi tra parentesi quadre `[…]` vanno compilati al momento della firma. Le clausole obbligatorie ex Art. 28(3) GDPR sono già predisposte e non vanno modificate senza confronto legale.

---

## Parti

| Ruolo | Soggetto |
|---|---|
| **Titolare del trattamento** (di seguito "Cliente" o "Titolare") | `[Ragione sociale Cliente]`, P.IVA `[…]`, sede legale `[…]`, in persona del legale rappresentante / DPO `[…]` |
| **Responsabile del trattamento** (di seguito "NormaAI") | NormaAI S.r.l., P.IVA `[…]`, sede legale `[…]`, contatto privacy: privacy@normaai.org |

Le Parti, premesso che il Cliente utilizza il servizio NormaAI di analisi automatizzata di conformità normativa europea (di seguito il "Servizio"), e che nell'erogazione del Servizio NormaAI tratta dati personali per conto del Cliente, concordano quanto segue ai sensi dell'Art. 28 GDPR.

---

## 1. Oggetto, durata, natura e finalità del trattamento

**1.1 Oggetto.** Il trattamento ha ad oggetto i dati personali contenuti nei dati aziendali che il Cliente conferisce al Servizio (profili aziendali, query di compliance, documenti caricati per analisi, metadati di utilizzo) ai fini dell'analisi di conformità normativa europea.

**1.2 Natura e finalità.** Il trattamento è svolto esclusivamente per erogare il Servizio: ricezione, archiviazione, elaborazione tramite modelli di intelligenza artificiale e restituzione al Cliente delle analisi di conformità (es. score, gap analysis, raccomandazioni). NormaAI non tratta i dati per finalità proprie diverse dall'erogazione del Servizio.

**1.3 Durata.** Il trattamento ha la stessa durata del contratto di servizio sottostante. Alla cessazione si applica l'art. 8 del presente Accordo (cancellazione/restituzione).

**1.4 Base giuridica del Titolare.** Il Cliente, in qualità di Titolare, è responsabile dell'individuazione della base giuridica del trattamento ex Art. 6 GDPR e garantisce di disporre di una valida base per il conferimento dei dati a NormaAI.

---

## 2. Categorie di interessati e tipologie di dati

**2.1 Categorie di interessati.** A titolo indicativo: dipendenti, collaboratori, referenti aziendali e altri soggetti i cui dati personali siano eventualmente contenuti nei documenti e nelle query che il Cliente sottopone al Servizio.

**2.2 Tipologie di dati personali.**
- Profili aziendali (settore, dimensione, fatturato, giurisdizioni) — nella misura in cui contengano dati riferibili a persone fisiche.
- Query di compliance e cronologia delle conversazioni.
- Documenti caricati per l'analisi (il cui contenuto è determinato unilateralmente dal Cliente).
- Metadati di utilizzo del Servizio (log tecnici, identificativi utente, timestamp, indirizzo IP).

**2.3 Categorie particolari di dati (Art. 9 GDPR).** Il Servizio non è progettato per il trattamento di categorie particolari di dati. Il Cliente si impegna a non caricare dati ex Art. 9/10 GDPR salvo preventivo accordo scritto e adozione di misure aggiuntive.

---

## 3. Obblighi del Responsabile (NormaAI)

Ai sensi dell'Art. 28(3) GDPR, NormaAI si impegna a:

1. **trattare i dati solo su istruzione documentata** del Titolare (il presente Accordo e il contratto di servizio costituiscono le istruzioni iniziali), anche per i trasferimenti verso Paesi terzi, salvo obblighi di legge UE/Stato membro (nel qual caso ne informa il Titolare prima del trattamento, salvo divieto di legge);
2. **garantire la riservatezza**, assicurando che le persone autorizzate al trattamento si siano impegnate alla riservatezza o vi siano soggette per legge;
3. **adottare misure tecniche e organizzative adeguate** ex Art. 32 GDPR (vedi art. 4);
4. rispettare le **condizioni per il ricorso a sub-responsabili** (vedi art. 5);
5. **assistere il Titolare** con misure tecniche e organizzative adeguate per dar seguito alle richieste di esercizio dei diritti degli interessati (vedi art. 6);
6. **assistere il Titolare** nel garantire il rispetto degli obblighi ex Artt. 32–36 GDPR (sicurezza, notifica violazioni, DPIA, consultazione preventiva), tenuto conto della natura del trattamento e delle informazioni disponibili;
7. su scelta del Titolare, **cancellare o restituire** tutti i dati personali al termine del Servizio (vedi art. 8);
8. mettere a disposizione del Titolare **tutte le informazioni necessarie** a dimostrare il rispetto degli obblighi e consentire e contribuire alle **attività di audit** (vedi art. 9);
9. **informare immediatamente** il Titolare qualora, a suo parere, un'istruzione violi il GDPR o altre disposizioni in materia di protezione dei dati.

---

## 4. Misure di sicurezza (Art. 32 GDPR)

Tenuto conto dello stato dell'arte e dei rischi, NormaAI adotta in particolare:

- **Crittografia** dei dati in transito (TLS 1.3) e at rest (AES-256 su database e backup).
- **Isolamento multi-tenant** tramite PostgreSQL Row Level Security (RLS).
- **Controllo accessi**: RBAC granulare, segregazione dei compiti (four-eyes), SSO enterprise (SAML 2.0 / OIDC), rate limiting, revoca immediata token.
- **Audit trail** completo degli eventi con timestamp, utente e IP, conservato come da policy di sicurezza.
- **Riservatezza** delle credenziali (hashing bcrypt, rotazione automatica dei token).
- **Resilienza e ripristino**: backup cifrati e procedure di disponibilità del Servizio.

Le misure di dettaglio sono descritte nella pagina pubblica di sicurezza ([/security](https://normaai.org/security)) e possono essere aggiornate purché il livello di protezione non sia ridotto.

---

## 5. Sub-responsabili del trattamento (Art. 28(2) e (4))

**5.1 Autorizzazione generale.** Il Titolare autorizza il ricorso ai sub-responsabili elencati di seguito. NormaAI stipula con ciascun sub-responsabile un contratto che impone obblighi di protezione dei dati equivalenti a quelli del presente Accordo e resta pienamente responsabile verso il Titolare per l'operato dei sub-responsabili.

**5.2 Elenco sub-responsabili autorizzati:**

| Sub-responsabile | Trattamento | Localizzazione / trasferimento extra-UE | Garanzie |
|---|---|---|---|
| **Google LLC** (Google Gemini API) | Elaborazione AI delle query e dei documenti | USA / possibile trasferimento | Standard Contractual Clauses (SCC) + EU-US Data Privacy Framework (DPF) |
| **Resend** (provider email transazionale) | Invio di comunicazioni e notifiche di servizio | USA / possibile trasferimento | Standard Contractual Clauses (SCC) |
| **Hetzner** (hosting / infrastruttura cloud) | Hosting applicativo e database con data residency UE | UE (Germania) | Trattamento all'interno dello SEE; nessun trasferimento extra-UE |

**5.3 Modifiche.** NormaAI informa il Titolare di eventuali modifiche relative all'aggiunta o sostituzione di sub-responsabili con **almeno 30 giorni di preavviso**, dando al Titolare la possibilità di opporsi per motivi ragionevoli e documentati. In caso di opposizione non risolvibile, ciascuna Parte può recedere dalla parte di Servizio interessata.

---

## 6. Assistenza per i diritti degli interessati (Artt. 12–23)

NormaAI assiste il Titolare, con misure tecniche e organizzative adeguate e nella misura del possibile, a dar seguito alle richieste degli interessati relative a: accesso, rettifica, cancellazione, limitazione, portabilità e opposizione. Qualora una richiesta dell'interessato pervenga direttamente a NormaAI, questa non vi dà autonomamente seguito ma la trasmette senza ingiustificato ritardo al Titolare, indirizzando l'interessato al Titolare medesimo.

---

## 7. Violazioni dei dati personali — notifica (Artt. 33–34 GDPR)

**7.1 Notifica al Titolare.** NormaAI notifica al Titolare ogni violazione di dati personali **senza ingiustificato ritardo e comunque entro 48 ore** dal momento in cui ne è venuta a conoscenza, così da consentire al Titolare di adempiere ai propri obblighi (di norma notifica all'Autorità di controllo entro 72 ore ex Art. 33).

**7.2 Contenuto minimo della notifica** (ex Art. 33(3)), nella misura delle informazioni disponibili:
- natura della violazione, categorie e numero approssimativo di interessati e di record coinvolti;
- nome e contatti del punto di riferimento NormaAI (security@normaai.org) per ulteriori informazioni;
- probabili conseguenze della violazione;
- misure adottate o proposte per porvi rimedio e per attenuarne i possibili effetti negativi.

**7.3 Cooperazione.** NormaAI coopera con il Titolare e adotta le misure correttive ragionevoli; ove non tutte le informazioni siano disponibili al momento della prima notifica, le fornisce successivamente in fasi senza ulteriore ingiustificato ritardo. NormaAI non effettua comunicazioni a terzi (interessati, Autorità, media) in merito alla violazione senza previo coordinamento con il Titolare, salvo obblighi di legge.

---

## 8. Cancellazione o restituzione dei dati a fine contratto

Alla cessazione del Servizio, a scelta del Titolare, NormaAI **cancella** oppure **restituisce** tutti i dati personali trattati per conto del Titolare e cancella le copie esistenti, salvo che il diritto UE o dello Stato membro richieda la conservazione. In coerenza con la policy di conservazione del Servizio, la cancellazione è completata **entro 90 giorni** dal termine del contratto. Su richiesta, NormaAI fornisce attestazione scritta dell'avvenuta cancellazione.

---

## 9. Audit e ispezioni (Art. 28(3)(h))

NormaAI mette a disposizione del Titolare le informazioni necessarie a dimostrare la conformità agli obblighi del presente Accordo e consente e contribuisce ad audit, anche tramite ispezioni, condotti dal Titolare o da un revisore da questi incaricato. Gli audit sono concordati con ragionevole preavviso (di norma **almeno 14 giorni**), svolti in orari lavorativi, in modo da non compromettere la sicurezza degli altri clienti e con costi a carico del Titolare salvo che l'audit riveli una non conformità sostanziale. Su richiesta, NormaAI può soddisfare l'obbligo fornendo report di certificazione/audit di terzi (es. SOC 2, una volta disponibile).

---

## 10. Disposizioni finali

**10.1 Gerarchia.** In caso di conflitto tra il presente Accordo e il contratto di servizio relativamente alla protezione dei dati, prevale il presente Accordo. In caso di conflitto con il GDPR, prevale il GDPR.

**10.2 Legge applicabile e foro.** Il presente Accordo è regolato dalla legge italiana; per quanto non previsto si rinvia al GDPR e alla normativa nazionale applicabile.

**10.3 Modifiche.** Eventuali modifiche sono concordate per iscritto tra le Parti.

---

### Firme

| Titolare (Cliente) | Responsabile (NormaAI S.r.l.) |
|---|---|
| Nome: `[…]` | Nome: `[…]` |
| Ruolo: `[…]` | Ruolo: `[…]` |
| Data: `[…]` | Data: `[…]` |
| Firma: ____________________ | Firma: ____________________ |

---

*Documento generato come template contrattuale. Da rivedere con consulenza legale prima della firma del primo pilot. Riferimenti incrociati: Privacy Policy (/privacy), Termini di Servizio (/terms), pagina Sicurezza (/security).*
