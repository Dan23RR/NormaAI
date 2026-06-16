"""
Synthetic Document Generator — Red Team Adversarial Testing.

Generates realistic regulatory documents with intentionally injected flaws
at 5 difficulty levels for testing NormaAI's detection capabilities.

The "Regulatory War Games" architecture:
- RED TEAM (this module): Generates flawed documents
- BLUE TEAM (NormaAI): Detects the flaws
- REFEREE (LLM Judge): Evaluates detection quality

Usage:
    python -m tests.validation.synthetic_generator --framework GDPR --level 3 --count 10
"""

import argparse
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "test_cases" / "synthetic"


# ─── Flaw Catalog ──────────────────────────────────────────────
# Each flaw is a precise, article-specific defect to inject

FLAW_CATALOG = {
    "GDPR": {
        "level_1_obvious": [
            {
                "id": "GDPR-L1-001",
                "article": "Art. 13(2)(a)",
                "description": "Privacy policy senza periodo di conservazione dati",
                "injection": "remove_section",
                "target_section": "retention_period",
                "doc_type": "privacy_policy",
            },
            {
                "id": "GDPR-L1-002",
                "article": "Art. 28(3)(h)",
                "description": "DPA senza clausola di audit",
                "injection": "remove_section",
                "target_section": "audit_rights",
                "doc_type": "dpa",
            },
            {
                "id": "GDPR-L1-003",
                "article": "Art. 37",
                "description": "Nessuna menzione del DPO nella privacy policy",
                "injection": "remove_section",
                "target_section": "dpo_designation",
                "doc_type": "privacy_policy",
            },
            {
                "id": "GDPR-L1-004",
                "article": "Art. 33",
                "description": "Piano incidenti senza procedura notifica 72h al Garante",
                "injection": "remove_section",
                "target_section": "breach_notification_authority",
                "doc_type": "incident_response_plan",
            },
            {
                "id": "GDPR-L1-005",
                "article": "Art. 7(3)",
                "description": "Consent form senza meccanismo di revoca",
                "injection": "remove_section",
                "target_section": "withdrawal_mechanism",
                "doc_type": "consent_form",
            },
            {
                "id": "GDPR-L1-006",
                "article": "Art. 30",
                "description": "Assenza completa del registro dei trattamenti",
                "injection": "remove_document",
                "target_section": "processing_records",
                "doc_type": "ropa",
            },
            {
                "id": "GDPR-L1-007",
                "article": "Art. 35",
                "description": "Trattamento ad alto rischio senza DPIA",
                "injection": "remove_document",
                "target_section": "impact_assessment",
                "doc_type": "dpia",
            },
        ],
        "level_2_subtle": [
            {
                "id": "GDPR-L2-001",
                "article": "Art. 13(2)(a)",
                "description": "Periodo conservazione vago: 'per il tempo necessario'",
                "injection": "replace_with_vague",
                "target_section": "retention_period",
                "replacement": "I dati personali saranno conservati per il tempo strettamente necessario alle finalità del trattamento.",
                "doc_type": "privacy_policy",
            },
            {
                "id": "GDPR-L2-002",
                "article": "Art. 28(3)(h)",
                "description": "Clausola audit limitata a 'previo accordo scritto'",
                "injection": "replace_with_restrictive",
                "target_section": "audit_rights",
                "replacement": "Il Titolare potrà effettuare verifiche previo accordo scritto del Responsabile, limitatamente a quanto strettamente necessario e con preavviso di almeno 90 giorni lavorativi. L'audit sarà condotto a spese esclusive del Titolare.",
                "doc_type": "dpa",
            },
            {
                "id": "GDPR-L2-003",
                "article": "Art. 6(1)(a)",
                "description": "Consenso bundled con accettazione T&C generali",
                "injection": "replace_with_bundled",
                "target_section": "distinguishable_consent",
                "replacement": "Accettando i presenti Termini e Condizioni, l'utente acconsente al trattamento dei propri dati personali per tutte le finalità ivi descritte.",
                "doc_type": "consent_form",
            },
            {
                "id": "GDPR-L2-004",
                "article": "Art. 5(1)(c)",
                "description": "Raccolta dati eccessiva mascherata da 'servizio migliore'",
                "injection": "replace_with_excessive",
                "target_section": "purpose_and_legal_basis",
                "replacement": "I dati personali sono trattati per le seguenti finalità:\n- Erogazione del servizio richiesto\n- Miglioramento continuo dell'esperienza utente\n- Analisi comportamentale avanzata per personalizzazione\n- Profilazione a fini di marketing diretto e indiretto\n- Condivisione con partner commerciali per offerte personalizzate\n- Sviluppo di modelli predittivi basati su IA",
                "doc_type": "privacy_policy",
            },
            {
                "id": "GDPR-L2-005",
                "article": "Art. 13(1)(f)",
                "description": "Trasferimento extra-UE menzionato ma senza garanzie specifiche",
                "injection": "replace_with_vague",
                "target_section": "third_country_transfers",
                "replacement": "I dati potranno essere trasferiti verso paesi al di fuori dello Spazio Economico Europeo per ragioni operative. In tali casi, l'azienda adotta misure ragionevoli per la protezione dei dati.",
                "doc_type": "privacy_policy",
            },
        ],
        "level_3_adversarial": [
            {
                "id": "GDPR-L3-001",
                "article": "Art. 28(3)(h)",
                "description": "Clausola audit tecnicamente presente ma svuotata di contenuto",
                "injection": "replace_with_deceptive",
                "target_section": "audit_rights",
                "replacement": "Il Responsabile riconosce il diritto di audit del Titolare. Tale diritto è esercitabile esclusivamente tramite questionari scritti inviati al Responsabile, il quale fornirà risposte entro 60 giorni lavorativi. Ispezioni in loco non sono consentite per ragioni di sicurezza e riservatezza commerciale. Le risultanze dell'audit non sono vincolanti.",
                "doc_type": "dpa",
            },
            {
                "id": "GDPR-L3-002",
                "article": "Art. 17",
                "description": "Diritto alla cancellazione tecnicamente presente ma con eccezioni enormi",
                "injection": "replace_with_deceptive",
                "target_section": "data_subject_rights",
                "replacement": "L'interessato ha diritto alla cancellazione dei dati (Art. 17 GDPR). Tuttavia, il Titolare potrà non dare seguito alla richiesta qualora il trattamento sia necessario per: adempimenti contrattuali in essere o futuri, obblighi legali (inclusi quelli fiscali con termine di 10 anni), esercizio di diritti in sede giudiziaria, motivi di interesse pubblico, ricerca statistica, e qualsiasi altro motivo legittimo riconosciuto dal Titolare.",
                "doc_type": "privacy_policy",
            },
            {
                "id": "GDPR-L3-003",
                "article": "Art. 5(1)(b)",
                "description": "Finalità originaria che nasconde un purpose creep verso IA",
                "injection": "replace_with_deceptive",
                "target_section": "purpose_and_legal_basis",
                "replacement": "I dati personali sono trattati per:\n- Erogazione del servizio (Art. 6(1)(b))\n- Obblighi di legge (Art. 6(1)(c))\n- Legittimo interesse (Art. 6(1)(f)): inclusi ma non limitati a miglioramento del servizio, analisi aggregate, sviluppo tecnologico e innovazione attraverso sistemi di apprendimento automatico",
                "doc_type": "privacy_policy",
            },
        ],
        "level_4_cross_framework": [
            {
                "id": "GDPR-L4-001",
                "articles": ["Art. 22 GDPR", "Art. 14 AI Act"],
                "description": "Sistema IA conforme all'AI Act per documentazione tecnica ma viola GDPR Art. 22 per decisioni automatizzate senza salvaguardie",
                "injection": "cross_framework_conflict",
                "doc_type": "ai_system_documentation",
            },
            {
                "id": "GDPR-L4-002",
                "articles": ["Art. 5(1)(e) GDPR", "ESRS E1 CSRD"],
                "description": "Report CSRD che richiede dati storici pluriennali ma GDPR impone limiti alla conservazione",
                "injection": "cross_framework_tension",
                "doc_type": "sustainability_report",
            },
        ],
        "level_5_temporal": [
            {
                "id": "GDPR-L5-001",
                "article": "Art. 46",
                "description": "DPA con riferimento a Privacy Shield (invalidato da Schrems II nel 2020)",
                "injection": "replace_with_outdated",
                "target_section": "appropriate_safeguards",
                "replacement": "I trasferimenti di dati verso gli Stati Uniti d'America sono effettuati sulla base della Decisione di esecuzione (UE) 2016/1250 della Commissione (EU-US Privacy Shield), che garantisce un livello adeguato di protezione dei dati.",
                "doc_type": "dpa",
            },
            {
                "id": "GDPR-L5-002",
                "article": "Art. 32",
                "description": "Misure di sicurezza basate su standard obsoleto (Allegato B D.Lgs. 196/2003)",
                "injection": "replace_with_outdated",
                "target_section": "technical_measures",
                "replacement": "Le misure di sicurezza adottate sono conformi all'Allegato B del Codice Privacy (D.Lgs. 196/2003), come previsto dalla normativa vigente. In particolare: password di almeno 8 caratteri, aggiornamento antivirus semestrale, backup settimanale, DPS aggiornato annualmente.",
                "doc_type": "security_policy",
            },
        ],
    },
    "DORA": {
        "level_1_obvious": [
            {
                "id": "DORA-L1-001",
                "article": "Art. 6",
                "description": "Assenza completa del framework di gestione rischi ICT",
                "injection": "remove_document",
                "target_section": "risk_management_framework",
                "doc_type": "ict_risk_framework",
            },
            {
                "id": "DORA-L1-002",
                "article": "Art. 11",
                "description": "Nessun piano di risposta e ripristino ICT",
                "injection": "remove_section",
                "target_section": "response_recovery",
                "doc_type": "incident_response_plan",
            },
            {
                "id": "DORA-L1-003",
                "article": "Art. 30",
                "description": "Contratti ICT senza clausole contrattuali minime DORA",
                "injection": "remove_section",
                "target_section": "key_contractual_provisions",
                "doc_type": "third_party_policy",
            },
        ],
        "level_2_subtle": [
            {
                "id": "DORA-L2-001",
                "article": "Art. 24",
                "description": "Testing ICT generico senza frequenza e metodologia definite",
                "injection": "replace_with_vague",
                "target_section": "general_requirements",
                "replacement": "L'organizzazione conduce test periodici dei propri sistemi ICT in base alle risorse disponibili e alle necessità operative.",
                "doc_type": "testing_framework",
            },
            {
                "id": "DORA-L2-002",
                "article": "Art. 28",
                "description": "Policy fornitori ICT senza due diligence strutturata",
                "injection": "replace_with_vague",
                "target_section": "general_principles",
                "replacement": "I fornitori ICT sono selezionati in base a criteri di affidabilità e prezzo. Il monitoraggio avviene su base annuale.",
                "doc_type": "third_party_policy",
            },
        ],
    },
    "NIS2": {
        "level_1_obvious": [
            {
                "id": "NIS2-L1-001",
                "article": "Art. 23",
                "description": "Nessuna procedura di notifica incidenti al CSIRT",
                "injection": "remove_section",
                "target_section": "reporting_obligations",
                "doc_type": "incident_response_plan",
            },
            {
                "id": "NIS2-L1-002",
                "article": "Art. 21(2)(c)",
                "description": "Assenza piano di continuità operativa",
                "injection": "remove_document",
                "target_section": "business_continuity",
                "doc_type": "bcp",
            },
            {
                "id": "NIS2-L1-003",
                "article": "Art. 20",
                "description": "Governance sicurezza senza responsabilità del management",
                "injection": "remove_section",
                "target_section": "governance",
                "doc_type": "security_policy",
            },
        ],
        "level_2_subtle": [
            {
                "id": "NIS2-L2-001",
                "article": "Art. 21(2)(d)",
                "description": "Supply chain security limitata ai fornitori di primo livello",
                "injection": "replace_with_insufficient",
                "target_section": "supply_chain_security",
                "replacement": "I fornitori diretti sono valutati sotto il profilo della sicurezza al momento dell'onboarding.",
                "doc_type": "security_policy",
            },
        ],
    },
}


# ─── Document Templates (Italian, professional grade) ──────────

FULL_DOCUMENT_TEMPLATES = {
    "privacy_policy": """# Informativa sul Trattamento dei Dati Personali
## ai sensi degli Artt. 13 e 14 del Regolamento (UE) 2016/679 (GDPR)

### 1. Titolare del Trattamento
{company_name}, con sede legale in {address}, P.IVA {vat_number}, in persona del legale rappresentante pro tempore (di seguito "Titolare"), tratta i Suoi dati personali nel rispetto del Regolamento (UE) 2016/679 (GDPR) e della normativa nazionale applicabile.

Contatti: {email} | Tel: {phone}

### 2. Responsabile della Protezione dei Dati (DPO)
{dpo_section}

### 3. Categorie di Dati Trattati
Il Titolare tratta le seguenti categorie di dati personali:
- Dati identificativi (nome, cognome, codice fiscale, indirizzo)
- Dati di contatto (email, telefono)
- Dati di navigazione (indirizzo IP, cookie tecnici e analitici)
- Dati contrattuali (storico ordini, preferenze)

### 4. Finalità e Base Giuridica del Trattamento
{purpose_section}

### 5. Destinatari dei Dati
{recipients_section}

### 6. Trasferimenti verso Paesi Terzi
{transfers_section}

### 7. Periodo di Conservazione
{retention_section}

### 8. Diritti dell'Interessato
{rights_section}

### 9. Revoca del Consenso
{withdrawal_section}

### 10. Diritto di Reclamo
{complaint_section}

### 11. Processo Decisionale Automatizzato
{automated_section}

### 12. Obbligatorietà del Conferimento
{statutory_section}

Data ultimo aggiornamento: {update_date}
""",
    "dpa": """# Accordo sul Trattamento dei Dati Personali
## ai sensi dell'Art. 28 del Regolamento (UE) 2016/679

### Premesse
Il presente accordo (DPA) è stipulato tra:
- **Titolare del trattamento**: {company_name}
- **Responsabile del trattamento**: {processor_name}

### 1. Oggetto e Durata
Il Responsabile tratta dati personali per conto del Titolare nell'ambito della fornitura di {service_description}. Il trattamento ha durata pari alla durata del contratto principale.

### 2. Istruzioni Documentate
{instructions_section}

### 3. Riservatezza
{confidentiality_section}

### 4. Misure di Sicurezza
{security_section}

### 5. Sub-responsabili
{sub_processor_section}

### 6. Assistenza al Titolare
{assistance_section}

### 7. Cancellazione o Restituzione
{deletion_section}

### 8. Informazioni e Audit
{audit_section}

### 9. Trasferimenti Internazionali
{transfer_section}

Luogo e data: ________________
Firma Titolare: ________________
Firma Responsabile: ________________
""",
}


# ─── Flaw Injection Methods ───────────────────────────────────


def _apply_flaw(document_text: str, flaw: dict) -> str:
    """Apply a single flaw to a document, returning modified text."""
    injection_type = flaw.get("injection", "remove_section")

    if injection_type == "remove_section":
        # Find and remove the relevant section
        section = flaw.get("target_section", "")
        # Remove between section headers
        lines = document_text.split("\n")
        filtered = []
        skip = False
        for line in lines:
            if section.replace("_", " ").lower() in line.lower():
                skip = True
                continue
            if skip and line.startswith("###"):
                skip = False
            if not skip:
                filtered.append(line)
        return "\n".join(filtered)

    elif injection_type in (
        "replace_with_vague",
        "replace_with_restrictive",
        "replace_with_bundled",
        "replace_with_excessive",
        "replace_with_deceptive",
        "replace_with_outdated",
        "replace_with_insufficient",
    ):
        replacement = flaw.get("replacement", "")
        section = flaw.get("target_section", "")
        # Replace section content
        lines = document_text.split("\n")
        result = []
        replaced = False
        skip_content = False
        for line in lines:
            if section.replace("_", " ").lower() in line.lower() and not replaced:
                result.append(line)  # Keep header
                result.append(replacement)
                skip_content = True
                replaced = True
                continue
            if skip_content and line.startswith("###"):
                skip_content = False
            if not skip_content:
                result.append(line)
        return "\n".join(result)

    elif injection_type == "remove_document":
        return f"[DOCUMENTO NON DISPONIBILE: {flaw.get('doc_type', 'unknown')} non ancora redatto]"

    return document_text


# ─── Synthetic Test Case Builder ───────────────────────────────


def _fill_template(template_name: str, company_info: dict, flaws: list[dict]) -> str:
    """Fill a document template with company info and apply flaws."""
    template = FULL_DOCUMENT_TEMPLATES.get(template_name)
    if not template:
        # Fallback: generate a basic document
        template = f"# Documento: {template_name}\n\nContenuto del documento per {company_info.get('company_name', 'Azienda')}."

    # Default section content
    defaults = {
        "company_name": company_info.get("company_name", "Test Company S.r.l."),
        "address": company_info.get("address", "Via Roma 1, 20121 Milano"),
        "vat_number": company_info.get("vat_number", "IT12345678901"),
        "email": company_info.get("email", "info@testcompany.it"),
        "phone": company_info.get("phone", "+39 02 1234567"),
        "domain": company_info.get("domain", "testcompany.it"),
        "processor_name": "Cloud Services Provider S.r.l.",
        "service_description": "servizi di hosting e gestione database",
        "update_date": datetime.now().strftime("%d/%m/%Y"),
        "dpo_section": "Il DPO è raggiungibile all'indirizzo: dpo@testcompany.it",
        "purpose_section": "I dati sono trattati per:\n- Esecuzione contrattuale (Art. 6(1)(b))\n- Obblighi legali (Art. 6(1)(c))\n- Legittimo interesse (Art. 6(1)(f)): miglioramento servizi",
        "recipients_section": "I dati potranno essere comunicati a fornitori IT, consulenti e autorità.",
        "transfers_section": "I trasferimenti verso paesi terzi avvengono con SCC ai sensi dell'Art. 46 GDPR.",
        "retention_section": "I dati sono conservati per massimo 10 anni dalla cessazione del rapporto.",
        "rights_section": "L'interessato ha diritto di accesso, rettifica, cancellazione, limitazione, portabilità e opposizione.",
        "withdrawal_section": "Il consenso può essere revocato in qualsiasi momento scrivendo a privacy@testcompany.it.",
        "complaint_section": "L'interessato può proporre reclamo al Garante per la Protezione dei Dati Personali.",
        "automated_section": "Non sono adottati processi decisionali automatizzati di cui all'Art. 22 GDPR.",
        "statutory_section": "Il conferimento è necessario per l'esecuzione del contratto.",
        "instructions_section": "Il Responsabile tratta i dati solo su istruzioni documentate del Titolare.",
        "confidentiality_section": "Il personale è vincolato alla riservatezza.",
        "security_section": "Sono adottate misure ai sensi dell'Art. 32 GDPR.",
        "sub_processor_section": "Sub-responsabili solo con autorizzazione scritta del Titolare.",
        "assistance_section": "Il Responsabile assiste il Titolare per le richieste degli interessati.",
        "deletion_section": "Al termine, i dati sono cancellati o restituiti.",
        "audit_section": "Il Titolare ha diritto di audit con preavviso ragionevole di 30 giorni.",
        "transfer_section": "Trasferimenti extra-UE solo con garanzie adeguate (Art. 46 GDPR).",
    }

    # Fill template
    text = template
    for key, value in defaults.items():
        text = text.replace(f"{{{key}}}", value)

    # Apply flaws
    for flaw in flaws:
        text = _apply_flaw(text, flaw)

    return text


def generate_synthetic_test_case(
    framework: str,
    level: int,
    flaw_ids: list[str] = None,
    company_info: dict = None,
) -> dict:
    """
    Generate a single synthetic test case.

    Args:
        framework: Target framework (GDPR, DORA, NIS2)
        level: Difficulty level (1-5)
        flaw_ids: Specific flaw IDs to inject (or None for all at level)
        company_info: Custom company info

    Returns:
        TestCase dict ready for JSON serialization
    """
    level_key = {
        1: "level_1_obvious",
        2: "level_2_subtle",
        3: "level_3_adversarial",
        4: "level_4_cross_framework",
        5: "level_5_temporal",
    }.get(level, "level_1_obvious")

    fw_flaws = FLAW_CATALOG.get(framework, {})
    available_flaws = fw_flaws.get(level_key, [])

    if flaw_ids:
        selected_flaws = [f for f in available_flaws if f["id"] in flaw_ids]
    else:
        selected_flaws = available_flaws

    if not selected_flaws:
        logger.warning(f"No flaws found for {framework} level {level}")
        return None

    info = company_info or {
        "company_name": "Synthetic Test S.r.l.",
        "sector": "technology",
        "address": "Via Test 1, 20100 Milano",
        "email": "info@synthetictest.it",
        "domain": "synthetictest.it",
    }

    # Determine document type from first flaw
    doc_type = selected_flaws[0].get("doc_type", "privacy_policy")

    # Generate document with flaws
    document_text = _fill_template(doc_type, info, selected_flaws)

    # Build expected findings
    expected = []
    for flaw in selected_flaws:
        articles = flaw.get("articles", [flaw.get("article", "")])
        if isinstance(articles, str):
            articles = [articles]
        for art in articles:
            if art:
                expected.append(
                    {
                        "framework": framework,
                        "article": art.replace(f" {framework}", "")
                        .replace(" GDPR", "")
                        .replace(" AI Act", ""),
                        "violation_type": {
                            "remove_section": "omission",
                            "remove_document": "omission",
                            "replace_with_vague": "insufficient",
                            "replace_with_restrictive": "insufficient",
                            "replace_with_bundled": "conflicting",
                            "replace_with_excessive": "conflicting",
                            "replace_with_deceptive": "ambiguous",
                            "replace_with_outdated": "outdated",
                            "replace_with_insufficient": "insufficient",
                            "cross_framework_conflict": "conflicting",
                            "cross_framework_tension": "conflicting",
                        }.get(flaw["injection"], "omission"),
                        "severity": "critical" if level >= 3 else "major",
                        "description": flaw["description"],
                    }
                )

    flaw_id_str = "_".join(f["id"] for f in selected_flaws)
    case_hash = hashlib.md5(flaw_id_str.encode()).hexdigest()[:6]
    case_id = f"SYN-{framework}-L{level}-{case_hash}"

    return {
        "id": case_id,
        "name": f"[Synthetic L{level}] {framework} — {selected_flaws[0]['description'][:80]}",
        "description": f"Documento sintetico con {len(selected_flaws)} difetti iniettati a livello {level}",
        "source_type": "synthetic",
        "synthetic_source": {
            "generator_model": "normaai-synthetic-generator-v1",
            "generation_prompt_hash": case_hash,
            "difficulty_level": level,
            "flaw_injection_method": "targeted_" + selected_flaws[0]["injection"],
        },
        "task_type": "gap_analysis",
        "query": framework,
        "document": {
            "document_type": doc_type,
            "content": document_text,
            "language": "it",
            "industry": info.get("sector", "technology"),
            "company_size": "PMI",
        },
        "company_profile": {
            "name": info["company_name"],
            "sector": info.get("sector", "technology"),
            "employee_count": 50,
            "revenue_eur": 5000000,
            "jurisdictions": ["IT", "EU"],
            "applicable_frameworks": [framework],
            "existing_documents": document_text,
        },
        "expected_findings": expected,
        "expected_not_findings": [],
        "difficulty": level,
        "tags": [framework.lower(), f"level_{level}", "synthetic", doc_type],
        "enabled": True,
    }


def generate_batch(
    framework: str = "GDPR",
    levels: list[int] = None,
) -> list[dict]:
    """Generate a batch of synthetic test cases for all flaws at specified levels."""
    if levels is None:
        levels = [1, 2, 3, 5]

    cases = []
    fw_flaws = FLAW_CATALOG.get(framework, {})

    for level in levels:
        level_key = {
            1: "level_1_obvious",
            2: "level_2_subtle",
            3: "level_3_adversarial",
            4: "level_4_cross_framework",
            5: "level_5_temporal",
        }.get(level, "level_1_obvious")

        flaws = fw_flaws.get(level_key, [])
        for flaw in flaws:
            flaw_id = flaw.get("id") or flaw.get("articles", ["unknown"])[0]
            tc = generate_synthetic_test_case(framework, level, [flaw_id])
            if tc:
                cases.append(tc)

    return cases


def save_synthetic_cases(cases: list[dict], filename: str = None) -> Path:
    """Save synthetic test cases to JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"synthetic_batch_{timestamp}.json"

    path = OUTPUT_DIR / filename
    path.write_text(
        json.dumps({"test_cases": cases}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"Saved {len(cases)} synthetic test cases to {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description="NormaAI Synthetic Test Generator")
    parser.add_argument("--framework", default="GDPR", help="Framework (GDPR, DORA, NIS2)")
    parser.add_argument("--level", type=int, nargs="+", default=[1, 2, 3, 5])
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    cases = generate_batch(framework=args.framework, levels=args.level)
    path = save_synthetic_cases(cases, args.output)
    print(f"Generated {len(cases)} synthetic test cases → {path}")


if __name__ == "__main__":
    main()
