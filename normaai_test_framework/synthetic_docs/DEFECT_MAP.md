# NormaAI Test Framework — Mappa dei Difetti Iniettati nei Documenti Sintetici

Questo file è il "foglio segreto" — contiene l'elenco esatto dei difetti iniettati
intenzionalmente in ogni documento sintetico. **Non condividerlo con il sistema sotto test.**

---

## 1. DPA_TalentLens_FLAWED.md

| # | Difetto | Articolo Violato | Sezione nel Doc |
|---|---------|------------------|-----------------|
| 1 | **Nessuna clausola di audit** — Il DPA non include il diritto del Controller di effettuare audit o ispezioni | Art. 28(3)(h) GDPR | Assente (manca completamente) |
| 2 | **Retention indefinita** — Sezione 6 dichiara retention "indefinite" per model training | Art. 5(1)(e) GDPR (storage limitation) + Art. 28(3)(g) | Sezione 6 |
| 3 | **Sub-processor non specificati** — Sezione 7 dà "general authorization" senza elencare i sub-processor | Art. 28(2) GDPR (richiede informazione specifica) | Sezione 7 |
| 4 | **Trasferimento USA senza SCC** — Sezione 8 menziona analytics partner USA senza SCCs | Art. 46 GDPR | Sezione 8 |
| 5 | **Nessuna cancellazione a fine servizio** — Sezione 10 esonera i dati di training dalla cancellazione | Art. 28(3)(g) GDPR | Sezione 10 |

---

## 2. Privacy_Policy_VisionGuard_FLAWED.md

| # | Difetto | Articolo Violato | Sezione nel Doc |
|---|---------|------------------|-----------------|
| 1 | **Biometria non dichiarata** — Non menziona affatto che il sistema crea profili biometrici individuali (gait, body) | Art. 9 GDPR (special categories) + Art. 13(1)(c) | Sezione 2 (omissione) |
| 2 | **Consenso invalido** — Consent buried in employment contract, non freely given (power imbalance) | Art. 7 GDPR + EDPB Guidelines 05/2020 | Sezione 5 |
| 3 | **No menzione decisioni automatizzate** — Nessuna disclosure su automated decision-making o profiling | Art. 13(2)(f) + Art. 22 GDPR | Assente |
| 4 | **Trasferimento USA senza safeguard** — Analytics partner USA senza SCCs menzionate | Art. 46 GDPR | Sezione 6 |
| 5 | **Base giuridica errata per biometria** — Usa "legitimate interest" per dati biometrici, che richiede Art. 9(2)(a) explicit consent | Art. 9(2) GDPR | Sezione 4 |

---

## 3. Sustainability_Report_GreenGrid_FLAWED.md

| # | Difetto | Articolo Violato | Sezione nel Doc |
|---|---------|------------------|-----------------|
| 1 | **Gas non conforme a TSC** — Le centrali a gas emettono 285g CO2e/kWh (> soglia 270g CDA) ma sono dichiarate Taxonomy-aligned | Art. 3 Taxonomy Reg. + CDA TSC | Sezione 1.2 + 2.3 |
| 2 | **Nessun DNSH biodiversità per eolico offshore** — Sezione 3.2 non menziona una valutazione DNSH specifica per impatti marini | Art. 17 Taxonomy Reg. | Sezione 3.2 |
| 3 | **Nessun target intermedio 2030** — Solo target 2050 net-zero, senza milestone intermedio come richiesto | ESRS E1-4 | Sezione 2.1 |
| 4 | **Nessun piano CAPEX allineato** — Report non include disclosure del CAPEX plan allineato alla Tassonomia | ESRS E1-7 + Art. 8 Taxonomy Reg. | Assente |
| 5 | **Nessun link remunerazione-sostenibilità** — La remunerazione dirigenziale NON è collegata a target ESG | ESRS 2 GOV-3 | Sezione 4.2 |
| 6 | **Greenwashing implicito** — CEO message dichiara 85% alignment senza disclosure delle limitazioni del calcolo gas | Art. 8 Taxonomy Reg. (principio di trasparenza) | CEO Message |
