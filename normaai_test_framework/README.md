# NormaAI Validation Framework

Framework di validazione completo per testare l'accuratezza degli agenti NormaAI
utilizzando dati sintetici con difetti di compliance iniettati intenzionalmente.

## Struttura

```
normaai_test_framework/
├── synthetic_profiles.py          # 5 profili aziendali con 25 gap noti
├── test_runner.py                 # Runner automatizzato per gli endpoint API
├── results_to_excel.py            # Importa i risultati JSON nell'Excel
├── NormaAI_Confusion_Matrix.xlsx  # Matrice di valutazione con dashboard
├── synthetic_docs/                # Documenti sintetici con errori iniettati
│   ├── DPA_TalentLens_FLAWED.md           # DPA con 5 errori GDPR
│   ├── Privacy_Policy_VisionGuard_FLAWED.md # Privacy policy con 5 errori
│   ├── Sustainability_Report_GreenGrid_FLAWED.md  # Report ESG con 6 errori
│   └── DEFECT_MAP.md              # Mappa segreta di tutti i difetti
└── README.md
```

## Quick Start

```bash
# 1. Assicurati che NormaAI sia in esecuzione
cd normaai && python -m src.api.main

# 2. Lancia i test (in un altro terminale)
cd normaai_test_framework
python test_runner.py --base-url http://localhost:8000 --delay 10

# 3. Importa i risultati nell'Excel
python results_to_excel.py test_results.json

# 4. Apri NormaAI_Confusion_Matrix.xlsx e controlla il Dashboard
```

## Profili Sintetici

| ID | Azienda | Framework | Test Cases |
|----|---------|-----------|------------|
| SYNTH-A | StahlWerk Industries GmbH | CSDDD, CSRD | 4 |
| SYNTH-B | VisionGuard SAS | AI Act, GDPR | 5 |
| SYNTH-C | Banca Credito Adriatico S.p.A. | DORA, NIS2, GDPR | 6 |
| SYNTH-D | GreenGrid Energy B.V. | Taxonomy, CSRD | 4 |
| SYNTH-E | TalentLens AI S.L. | AI Act, GDPR | 6 |

**Totale: 25 test cases** across 6 frameworks, 3 difficulty levels.

## Metriche di Valutazione

- **TRUE_POSITIVE**: L'agente ha trovato il gap con citazione corretta
- **PARTIAL_MATCH**: Concetto trovato, citazione imprecisa
- **FALSE_NEGATIVE**: Gap non trovato (bug critico)
- **ERROR**: Errore API
- **HALLUCINATION**: L'agente ha inventato un gap inesistente (da annotare manualmente)

**Target**: Detection Rate > 80%, Hallucination Rate < 10%
