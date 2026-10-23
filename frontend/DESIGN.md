# NormaAI: sistema di design (v2, ottobre 2026)

Questo documento è il brief che governa ogni pagina del frontend, pubblica e applicativa. Chi tocca l'interfaccia lo legge prima di scrivere codice e lo rispetta anche quando non lo cita.

## 1. Soggetto e lavoro da fare

NormaAI risponde a domande sul diritto dell'Unione (CSRD, CSDDD, AI Act, NIS2, DORA, GDPR, CRA, Tassonomia) con la fonte esatta: atto, articolo, passaggio testuale, link a EUR-Lex o Normattiva. Chi lo usa è un compliance officer, un consulente o un responsabile in una PMI italiana. Non compra "intelligenza artificiale": compra una risposta che può difendere davanti a un revisore.

Il lavoro dell'interfaccia è uno solo: far vedere che ogni affermazione poggia sul testo di legge, e portare la persona a quel testo in un gesto.

L'idea visiva è il **codice annotato**: il testo della norma al centro, le note nel margine, il passaggio che conta evidenziato con l'evidenziatore. È il modo in cui un giurista legge davvero una legge, e nessun altro prodotto SaaS si presenta così.

## 2. Colore

Chiaro di default, scuro opzionale (classe `dark` su `html`). I token vivono in `globals.css` come canali RGB e Tailwind li espone con supporto all'opacità (`bg-union/10`).

| Token | Chiaro | Uso |
|---|---|---|
| `canvas` | `#F1F2F4` | sfondo dell'applicazione, "la scrivania" |
| `surface` | `#FFFFFF` | il documento: pagine, pannelli, tabelle |
| `surface-2` | `#F7F8F9` | campi, intestazioni di tabella, riquadri secondari |
| `surface-3` | `#ECEEF1` | stato hover di righe e voci |
| `ink` | `#0C1B33` | testo principale: inchiostro blu-nero, non nero tinto |
| `ink-2` | `#3D4B61` | testo secondario |
| `ink-3` | `#6B7788` | testo terziario, didascalie (mai sotto 12 px) |
| `rule` | `#D8DCE3` | filetti e bordi |
| `rule-2` | `#C3C9D3` | bordi dei campi, filetti marcati |
| `union` | `#0A3A9C` | il blu dell'Unione: link, azioni primarie, focus |
| `union-deep` | `#072B75` | hover delle azioni primarie |
| `mark` | `#FFEA7A` | l'evidenziatore: **solo** per il passaggio di legge citato |
| `mark-deep` | `#F5C400` | il giallo delle stelle: icona del marchio, accenti del marchio |
| `ok` | `#137A4B` | citazione verificata, operazione riuscita |
| `warn` | `#9A5B00` | attenzione, scadenza vicina, verifica consigliata |
| `bad` | `#A3262E` | errore, scadenza superata |

Regole:
- L'evidenziatore è la cosa memorabile e si spende in un posto solo: la citazione testuale della norma. Mai come sfondo decorativo, mai nei bottoni.
- Il blu `union` è il colore delle azioni, non del marchio: il marchio è inchiostro più evidenziatore.
- Niente gradienti, niente ombre su ogni card. L'ombra `shadow-doc` esiste per due cose: il documento in primo piano nella hero e i dialoghi.
- I colori dei framework (`fw-*`) servono solo come etichetta di categoria, con testo scuro su tinta chiara, mai come riempimento pieno.

## 3. Tipografia

Due famiglie, entrambe self-hosted via `next/font`:

- **Literata** (`font-serif`): il testo della legge, i titoli, le citazioni. È un carattere nato per leggere a lungo su schermo, con assi ottici: a 44 px è un titolo, a 16 px è un comma.
- **Public Sans** (`font-sans`): l'interfaccia. Neutro, istituzionale, con cifre tabellari (`tabular-nums`) per date, soglie e CELEX.
- Geist Mono solo per chiavi API e codice. I numeri CELEX e gli articoli vanno in Public Sans tabellare, non in mono.

Scala (px / interlinea):
- display 44/1.1 (hero), `h1` 32/1.15, `h2` 24/1.2, `h3` 20/1.3, `h4` 17/1.4: Literata 500.
- corpo 16/1.55 pubblico, 15/1.5 applicazione: Public Sans 400.
- piccolo 13/1.45, didascalia 12/1.4. **Niente sotto 12 px.**
- Testo di legge citato: Literata 16/1.6, corsivo solo per i titoli degli atti.

Regole:
- Frasi in minuscolo con iniziale maiuscola. Mai etichette in maiuscoletto spaziato sopra i titoli.
- Mai una sola parola colorata o in corsivo dentro un titolo per "dare enfasi".
- Larghezza di riga: 60-75 caratteri per il corpo, fino a 80 per il serif.

## 4. Layout

Allineamento a sinistra ovunque; i numeri a destra nelle tabelle.

Pagine pubbliche: colonna massima 1120 px, gutter 24 px, sezioni separate da un filetto `rule` e da spazio, non da card.

```
┌──────────────────────────────────────────────────────────────┐
│ NormaAI                     Metodo  Prezzi  Accedi  [Prova]  │
├──────────────────────────────────────────────────────────────┤
│ Titolo in Literata, due righe         ┌────────────────────┐ │
│ sottotitolo                           │ Domanda             │ │
│ [Fai una domanda]  [Verifica l'ambito]│ Risposta            │ │
│                                       │ ┃ «passaggio di     │ │
│                                       │ ┃  legge evidenz.»  │ │
│                                       │   Reg. (UE) 2024/   │ │
│                                       │   1689, art. 50 ✓   │ │
│                                       └────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

Applicazione: barra laterale di 232 px (64 px compressa) con il marchio in alto e l'organizzazione in basso; intestazione di pagina con titolo e azioni; contenuto con larghezza massima 1200 px. La pagina Chiedi ha due colonne: la conversazione (massimo 72 caratteri) e il margine delle fonti, fisso durante lo scorrimento.

```
┌──────┬───────────────────────────────┬──────────────────────┐
│ Marc.│ Chiedi                        │ Fonti                │
│      │                               │                      │
│ Chie.│ Domanda                       │ 1 Reg. (UE) 2024/1689│
│ Ambi.│ Risposta con rimandi [1] [2]  │   art. 50, par. 1    │
│ Moni.│                               │   ┃«testo evidenz.»  │
│ Clie.│                               │   ✓ verificata       │
│ Repo.│                               │   EUR-Lex ↗          │
│      │                               │                      │
│ Org. │ [Scrivi la domanda      ][Inv]│ corpus al 2026-10-01 │
└──────┴───────────────────────────────┴──────────────────────┘
```

Tabelle: filetti orizzontali, niente zebra, intestazione in `ink-2` a 13 px. Card solo per entità discrete (un cliente, un report), mai per spezzettare un testo.

## 5. Principi

1. La fonte è la protagonista. Ogni risposta mostra il passaggio citato nel testo originale, l'atto e l'articolo, lo stato di verifica e il link alla banca dati ufficiale.
2. Tutto è datato: data del corpus, data della verifica, scadenze. Formato esteso in italiano ("2 agosto 2026") nel testo, ISO nelle tabelle.
3. Stati onesti: un vuoto invita a fare, un errore dice cosa è successo e cosa fare, un caricamento dice cosa sta caricando. Nessun pallino "attivo" su dati statici, nessun dato finto fuori dalla demo, e la demo è dichiarata.
4. Un marchio solo, pubblico e applicativo, chiaro di default.
5. Soglia di qualità non negoziabile: responsive fino a 360 px, focus visibile (2 px `union`, offset 2 px), contrasto AA, movimento ridotto rispettato, nessun testo sotto 12 px.
6. Movimento solo come risposta a un gesto (apri, espandi, conferma) e per il flusso della risposta. Nessuna animazione d'ingresso.

## 6. Scrittura

- Italiano, forma diretta, frasi corte. Inglese solo per termini tecnici consolidati.
- Il bottone dice cosa succede: "Invia la domanda", "Scarica il Codex", "Salva le modifiche". Mai "Submit", mai "Invia" da solo.
- Lo stesso nome lungo tutto il flusso: se il bottone dice "Pubblica", la conferma dice "Pubblicato".
- Errori senza scuse e senza vaghezza: "Il server non risponde. Riprova tra un minuto o scrivi a info@normaai.org."
- Niente trattini lunghi nel testo: due punti, virgole o parentesi.
- La demo si chiama "Demo con dati di esempio" e lo ricorda in ogni pagina.

## 7. Inventario dei componenti (`src/components/ui`)

`Button` (primary, secondary, ghost, danger; sm, md, lg; `loading`), `Field` (label, help, error, `Input`, `Select`, `Textarea`), `Badge` (neutral, union, ok, warn, bad, framework), `Card`, `Dialog`, `Table`, `Tabs`, `EmptyState`, `PageHeader`, `StatCard`, `Toast`, `Skeleton`, `LawQuote` (il passaggio evidenziato con margine), `SourceRow` (una fonte con stato), `Logo`, `SiteHeader`, `SiteFooter`, `AppShell`.

Il marchio: la parola "NormaAI" in Literata 600 con un tratto di evidenziatore giallo dietro "Norma". L'icona: quadrato inchiostro con una banda gialla e la N bianca.

## 8. Revisione del piano contro i default

- Carta calda, serif e accento argilla erano l'identità precedente e sono il default più riconoscibile delle pagine generate. Sostituiti con fondo bianco su scrivania neutra, inchiostro blu-nero, blu dell'Unione per le azioni e giallo evidenziatore per la fonte: tre scelte che vengono dal soggetto (la Gazzetta ufficiale, le stelle, l'evidenziatore sul codice).
- Il serif resta perché la legge si legge in serif, ma è Literata e serve al testo normativo, non a "fare editoriale".
- Niente etichette in maiuscoletto, niente puntini mediani tra i metadati, niente frecce appese ai link, niente mono per le etichette, niente numerazione 01/02/03 su contenuti che non sono una sequenza.
- Card rimosse come dispositivo di impaginazione; restano per le entità.
- Il rischio residuo è "SaaS blu": si evita usando il blu solo per le azioni e lasciando che inchiostro, evidenziatore e Literata portino l'identità.
