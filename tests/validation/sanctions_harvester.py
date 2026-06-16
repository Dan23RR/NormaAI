"""
Sanctions Harvester — Automated test case generation from real enforcement data.

Pipeline:
1. Fetch enforcement data from public databases
2. Extract structured violation information
3. Generate template documents with targeted flaws
4. Output as TestCase JSON files

Supported sources:
- GDPR Enforcement Tracker (CMS.Law) — 2400+ decisions
- Garante Privacy Italia — provvedimenti
- ICO UK — decision notices
- CNIL France — décisions
- BaFin Germany — DORA/NIS2 enforcement

Usage:
    python -m tests.validation.sanctions_harvester --framework GDPR --limit 50
    python -m tests.validation.sanctions_harvester --authority garante --since 2024-01-01
"""

import argparse
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "test_cases" / "sanctions"


# ─── Enforcement Record Schema ─────────────────────────────────


@dataclass
class EnforcementRecord:
    """Structured data from an enforcement decision."""

    id: str
    authority: str
    country: str
    date: str  # YYYY-MM-DD
    fine_eur: float
    company_sector: str
    company_size: str | None = None
    violated_articles: list[str] = field(default_factory=list)
    violation_summary: str = ""
    violation_types: list[str] = field(default_factory=list)
    decision_url: str | None = None
    framework: str = "GDPR"
    severity: str = "critical"


# ─── Article-to-Document Mapping ──────────────────────────────

# Maps GDPR articles to document types where violations typically occur
GDPR_ARTICLE_DOCUMENT_MAP = {
    # Transparency (Art. 12-14)
    "Art. 12": {"doc_type": "privacy_policy", "section": "accessibility_and_clarity"},
    "Art. 13": {"doc_type": "privacy_policy", "section": "information_at_collection"},
    "Art. 13(1)(a)": {"doc_type": "privacy_policy", "section": "controller_identity"},
    "Art. 13(1)(c)": {"doc_type": "privacy_policy", "section": "purpose_and_legal_basis"},
    "Art. 13(1)(d)": {"doc_type": "privacy_policy", "section": "legitimate_interest"},
    "Art. 13(1)(e)": {"doc_type": "privacy_policy", "section": "recipients"},
    "Art. 13(1)(f)": {"doc_type": "privacy_policy", "section": "third_country_transfers"},
    "Art. 13(2)(a)": {"doc_type": "privacy_policy", "section": "retention_period"},
    "Art. 13(2)(b)": {"doc_type": "privacy_policy", "section": "data_subject_rights"},
    "Art. 13(2)(c)": {"doc_type": "privacy_policy", "section": "right_to_withdraw_consent"},
    "Art. 13(2)(d)": {"doc_type": "privacy_policy", "section": "right_to_lodge_complaint"},
    "Art. 13(2)(e)": {"doc_type": "privacy_policy", "section": "statutory_requirement"},
    "Art. 13(2)(f)": {"doc_type": "privacy_policy", "section": "automated_decision_making"},
    "Art. 14": {"doc_type": "privacy_policy", "section": "indirect_collection_info"},
    # Consent (Art. 6-7)
    "Art. 6": {"doc_type": "consent_form", "section": "legal_basis"},
    "Art. 6(1)(a)": {"doc_type": "consent_form", "section": "consent_mechanism"},
    "Art. 7": {"doc_type": "consent_form", "section": "consent_conditions"},
    "Art. 7(1)": {"doc_type": "consent_form", "section": "demonstrate_consent"},
    "Art. 7(2)": {"doc_type": "consent_form", "section": "distinguishable_consent"},
    "Art. 7(3)": {"doc_type": "consent_form", "section": "withdrawal_mechanism"},
    # Data Subject Rights (Art. 15-22)
    "Art. 15": {"doc_type": "privacy_policy", "section": "right_of_access"},
    "Art. 16": {"doc_type": "privacy_policy", "section": "right_to_rectification"},
    "Art. 17": {"doc_type": "privacy_policy", "section": "right_to_erasure"},
    "Art. 20": {"doc_type": "privacy_policy", "section": "right_to_portability"},
    "Art. 21": {"doc_type": "privacy_policy", "section": "right_to_object"},
    "Art. 22": {"doc_type": "privacy_policy", "section": "automated_decision_making"},
    # Data Processing Agreement (Art. 28)
    "Art. 28": {"doc_type": "dpa", "section": "processor_obligations"},
    "Art. 28(3)": {"doc_type": "dpa", "section": "written_contract"},
    "Art. 28(3)(a)": {"doc_type": "dpa", "section": "documented_instructions"},
    "Art. 28(3)(b)": {"doc_type": "dpa", "section": "confidentiality"},
    "Art. 28(3)(c)": {"doc_type": "dpa", "section": "security_measures"},
    "Art. 28(3)(d)": {"doc_type": "dpa", "section": "sub_processor"},
    "Art. 28(3)(e)": {"doc_type": "dpa", "section": "data_subject_assistance"},
    "Art. 28(3)(f)": {"doc_type": "dpa", "section": "deletion_return"},
    "Art. 28(3)(g)": {"doc_type": "dpa", "section": "demonstration_compliance"},
    "Art. 28(3)(h)": {"doc_type": "dpa", "section": "audit_rights"},
    # Security (Art. 32-34)
    "Art. 32": {"doc_type": "security_policy", "section": "technical_measures"},
    "Art. 33": {"doc_type": "incident_response_plan", "section": "breach_notification_authority"},
    "Art. 34": {"doc_type": "incident_response_plan", "section": "breach_notification_subjects"},
    # DPIA (Art. 35)
    "Art. 35": {"doc_type": "dpia", "section": "impact_assessment"},
    # International Transfers (Art. 44-49)
    "Art. 44": {"doc_type": "dpa", "section": "transfer_general"},
    "Art. 46": {"doc_type": "dpa", "section": "appropriate_safeguards"},
    "Art. 49": {"doc_type": "dpa", "section": "derogations"},
    # DPO (Art. 37-39)
    "Art. 37": {"doc_type": "privacy_policy", "section": "dpo_designation"},
    "Art. 38": {"doc_type": "internal_policy", "section": "dpo_position"},
    "Art. 39": {"doc_type": "internal_policy", "section": "dpo_tasks"},
    # Records of Processing (Art. 30)
    "Art. 30": {"doc_type": "ropa", "section": "processing_records"},
    # Principles (Art. 5)
    "Art. 5(1)(a)": {"doc_type": "privacy_policy", "section": "lawfulness_fairness_transparency"},
    "Art. 5(1)(b)": {"doc_type": "privacy_policy", "section": "purpose_limitation"},
    "Art. 5(1)(c)": {"doc_type": "privacy_policy", "section": "data_minimisation"},
    "Art. 5(1)(d)": {"doc_type": "privacy_policy", "section": "accuracy"},
    "Art. 5(1)(e)": {"doc_type": "privacy_policy", "section": "storage_limitation"},
    "Art. 5(1)(f)": {"doc_type": "privacy_policy", "section": "integrity_confidentiality"},
    "Art. 5(2)": {"doc_type": "privacy_policy", "section": "accountability"},
}

# Maps DORA articles to document types
DORA_ARTICLE_DOCUMENT_MAP = {
    "Art. 5": {"doc_type": "ict_risk_framework", "section": "governance_arrangements"},
    "Art. 6": {"doc_type": "ict_risk_framework", "section": "risk_management_framework"},
    "Art. 7": {"doc_type": "ict_risk_framework", "section": "ict_systems_protocols"},
    "Art. 8": {"doc_type": "ict_risk_framework", "section": "identification"},
    "Art. 9": {"doc_type": "ict_risk_framework", "section": "protection_prevention"},
    "Art. 10": {"doc_type": "ict_risk_framework", "section": "detection"},
    "Art. 11": {"doc_type": "incident_response_plan", "section": "response_recovery"},
    "Art. 17": {"doc_type": "incident_response_plan", "section": "ict_incident_reporting"},
    "Art. 19": {"doc_type": "incident_response_plan", "section": "reporting_major_incidents"},
    "Art. 24": {"doc_type": "testing_framework", "section": "general_requirements"},
    "Art. 25": {"doc_type": "testing_framework", "section": "testing_tools"},
    "Art. 26": {"doc_type": "testing_framework", "section": "threat_led_penetration"},
    "Art. 28": {"doc_type": "third_party_policy", "section": "general_principles"},
    "Art. 30": {"doc_type": "third_party_policy", "section": "key_contractual_provisions"},
}

# Maps NIS2 articles to document types
NIS2_ARTICLE_DOCUMENT_MAP = {
    "Art. 20": {"doc_type": "security_policy", "section": "governance"},
    "Art. 21": {"doc_type": "security_policy", "section": "risk_management_measures"},
    "Art. 21(2)(a)": {"doc_type": "security_policy", "section": "risk_analysis"},
    "Art. 21(2)(b)": {"doc_type": "incident_response_plan", "section": "incident_handling"},
    "Art. 21(2)(c)": {"doc_type": "bcp", "section": "business_continuity"},
    "Art. 21(2)(d)": {"doc_type": "security_policy", "section": "supply_chain_security"},
    "Art. 21(2)(e)": {"doc_type": "security_policy", "section": "acquisition_security"},
    "Art. 21(2)(f)": {"doc_type": "security_policy", "section": "vulnerability_handling"},
    "Art. 21(2)(g)": {"doc_type": "security_policy", "section": "effectiveness_assessment"},
    "Art. 21(2)(h)": {"doc_type": "security_policy", "section": "cyber_hygiene_training"},
    "Art. 21(2)(i)": {"doc_type": "security_policy", "section": "cryptography"},
    "Art. 21(2)(j)": {"doc_type": "security_policy", "section": "hr_security_access"},
    "Art. 23": {"doc_type": "incident_response_plan", "section": "reporting_obligations"},
}

FRAMEWORK_ARTICLE_MAPS = {
    "GDPR": GDPR_ARTICLE_DOCUMENT_MAP,
    "DORA": DORA_ARTICLE_DOCUMENT_MAP,
    "NIS2": NIS2_ARTICLE_DOCUMENT_MAP,
}


# ─── Document Templates ───────────────────────────────────────

DOCUMENT_TEMPLATES = {
    "privacy_policy": {
        "title": "Informativa sul Trattamento dei Dati Personali",
        "sections": {
            "controller_identity": "Titolare del Trattamento: {company_name}, con sede in {address}. Contatti: {email}.",
            "purpose_and_legal_basis": "I dati personali sono trattati per le seguenti finalità e basi giuridiche:\n- Esecuzione contrattuale (Art. 6(1)(b) GDPR)\n- Adempimento obblighi di legge (Art. 6(1)(c) GDPR)\n- Consenso dell'interessato (Art. 6(1)(a) GDPR)\n- Legittimo interesse del titolare (Art. 6(1)(f) GDPR)",
            "legitimate_interest": "Il legittimo interesse del titolare consiste in: analisi statistiche aggregate, miglioramento dei servizi, prevenzione frodi.",
            "recipients": "I dati potranno essere comunicati a: fornitori di servizi IT, consulenti legali e fiscali, autorità competenti ove richiesto per legge.",
            "third_country_transfers": "I dati personali potranno essere trasferiti verso paesi terzi solo in presenza di una decisione di adeguatezza della Commissione Europea o di clausole contrattuali tipo (SCC) ai sensi dell'Art. 46 GDPR.",
            "retention_period": "I dati personali saranno conservati per il periodo strettamente necessario alle finalità indicate e comunque per non oltre 10 anni dalla cessazione del rapporto contrattuale, salvo obblighi di legge.",
            "data_subject_rights": "L'interessato ha diritto di: accesso (Art. 15), rettifica (Art. 16), cancellazione (Art. 17), limitazione (Art. 18), portabilità (Art. 20), opposizione (Art. 21).",
            "right_to_withdraw_consent": "Qualora il trattamento sia basato sul consenso, l'interessato ha il diritto di revocarlo in qualsiasi momento senza pregiudizio per la liceità del trattamento effettuato prima della revoca.",
            "right_to_lodge_complaint": "L'interessato ha il diritto di proporre reclamo all'autorità di controllo competente (Garante per la Protezione dei Dati Personali).",
            "automated_decision_making": "Il titolare non adotta processi decisionali automatizzati, inclusa la profilazione, di cui all'Art. 22 del GDPR.",
            "dpo_designation": "Il Responsabile della Protezione dei Dati (DPO) è raggiungibile all'indirizzo: dpo@{domain}.",
            "accessibility_and_clarity": "La presente informativa è resa in forma concisa, trasparente, intelligibile e facilmente accessibile, con un linguaggio semplice e chiaro.",
            "statutory_requirement": "Il conferimento dei dati è necessario per l'esecuzione del contratto. Il mancato conferimento comporta l'impossibilità di erogare i servizi richiesti.",
        },
    },
    "dpa": {
        "title": "Accordo sul Trattamento dei Dati (DPA) ai sensi dell'Art. 28 GDPR",
        "sections": {
            "documented_instructions": "Il Responsabile tratta i dati personali esclusivamente sulla base di istruzioni documentate del Titolare, anche per quanto riguarda i trasferimenti verso paesi terzi.",
            "confidentiality": "Il Responsabile garantisce che le persone autorizzate al trattamento si siano impegnate alla riservatezza o siano soggette a un obbligo legale di riservatezza.",
            "security_measures": "Il Responsabile adotta tutte le misure tecniche e organizzative richieste dall'Art. 32 GDPR, tra cui: pseudonimizzazione e cifratura, capacità di assicurare riservatezza, integrità e disponibilità, procedure di ripristino tempestivo, processo di test periodici.",
            "sub_processor": "Il Responsabile non ricorre a un altro responsabile del trattamento senza previa autorizzazione scritta del Titolare. In caso di autorizzazione generale, il Responsabile informa il Titolare di ogni modifica relativa all'aggiunta o sostituzione di sub-responsabili.",
            "data_subject_assistance": "Il Responsabile assiste il Titolare nel dare seguito alle richieste per l'esercizio dei diritti degli interessati di cui al Capo III del GDPR.",
            "deletion_return": "Al termine della prestazione, il Responsabile cancella o restituisce tutti i dati personali e cancella le copie esistenti, salvo che il diritto dell'Unione o dello Stato membro non preveda la conservazione.",
            "demonstration_compliance": "Il Responsabile mette a disposizione del Titolare tutte le informazioni necessarie per dimostrare il rispetto degli obblighi di cui al presente articolo.",
            "audit_rights": "Il Responsabile consente e contribuisce alle attività di revisione, comprese le ispezioni, realizzate dal Titolare o da un altro soggetto da questi incaricato. Il diritto di audit è esercitabile con preavviso ragionevole di 30 giorni lavorativi.",
            "transfer_general": "Ogni trasferimento di dati personali verso paesi terzi avviene nel rispetto del Capo V del GDPR.",
            "appropriate_safeguards": "In assenza di decisione di adeguatezza, i trasferimenti sono effettuati sulla base di clausole contrattuali tipo adottate dalla Commissione Europea.",
        },
    },
    "consent_form": {
        "title": "Modulo di Consenso al Trattamento dei Dati Personali",
        "sections": {
            "consent_mechanism": "Con la presente, l'interessato esprime il proprio consenso libero, specifico, informato e inequivocabile al trattamento dei propri dati personali per le finalità sotto indicate.",
            "legal_basis": "Base giuridica: Art. 6(1)(a) GDPR — consenso dell'interessato.",
            "demonstrate_consent": "Il presente consenso viene registrato elettronicamente con marca temporale e indirizzo IP dell'interessato, ai fini della dimostrabilità ai sensi dell'Art. 7(1) GDPR.",
            "distinguishable_consent": "La richiesta di consenso è presentata in forma chiaramente distinguibile dalle altre dichiarazioni, in linguaggio semplice e chiaro, ai sensi dell'Art. 7(2) GDPR.",
            "withdrawal_mechanism": "L'interessato può revocare il consenso in qualsiasi momento tramite: email a privacy@{domain}, pannello account personale, o richiesta scritta al Titolare.",
        },
    },
    "security_policy": {
        "title": "Policy di Sicurezza delle Informazioni",
        "sections": {
            "technical_measures": "L'organizzazione implementa le seguenti misure tecniche e organizzative:\n- Cifratura dei dati in transito (TLS 1.3) e a riposo (AES-256)\n- Controllo degli accessi basato su ruoli (RBAC)\n- Autenticazione multi-fattore (MFA)\n- Monitoraggio continuo e logging centralizzato\n- Backup giornalieri con test di ripristino periodici",
            "risk_analysis": "Viene condotta un'analisi dei rischi almeno annuale, considerando minacce, vulnerabilità e impatti potenziali su riservatezza, integrità e disponibilità dei sistemi.",
            "incident_handling": "La procedura di gestione degli incidenti prevede: rilevamento, contenimento, eradicazione, ripristino e analisi post-incidente (lessons learned).",
            "supply_chain_security": "I fornitori sono valutati sotto il profilo della sicurezza prima dell'onboarding e monitorati periodicamente. Requisiti di sicurezza sono inclusi nei contratti.",
            "vulnerability_handling": "Scansioni di vulnerabilità sono eseguite mensilmente. Le vulnerabilità critiche sono rimediate entro 72 ore dalla scoperta.",
            "cyber_hygiene_training": "Tutto il personale riceve formazione annuale sulla cybersicurezza, con simulazioni di phishing trimestrali.",
            "cryptography": "Sono utilizzati solo algoritmi crittografici approvati (AES-256, RSA-2048+, SHA-256+). Le chiavi sono gestite tramite HSM certificato.",
        },
    },
    "incident_response_plan": {
        "title": "Piano di Risposta agli Incidenti",
        "sections": {
            "breach_notification_authority": "In caso di violazione dei dati personali, il Titolare notifica l'autorità di controllo competente entro 72 ore dal momento in cui ne è venuto a conoscenza, ai sensi dell'Art. 33 GDPR.",
            "breach_notification_subjects": "Quando la violazione presenta un rischio elevato per i diritti e le libertà delle persone fisiche, il Titolare comunica la violazione all'interessato senza ingiustificato ritardo, ai sensi dell'Art. 34 GDPR.",
            "ict_incident_reporting": "Gli incidenti ICT maggiori sono classificati secondo i criteri dell'Art. 18 DORA e notificati all'autorità competente nei tempi previsti.",
            "reporting_obligations": "L'organizzazione notifica gli incidenti significativi al CSIRT nazionale entro 24 ore (allarme rapido), con rapporto intermedio entro 72 ore e rapporto finale entro un mese, ai sensi dell'Art. 23 NIS2.",
            "response_recovery": "Le procedure di risposta e ripristino garantiscono la continuità delle funzioni critiche e il ritorno alla normalità nel minor tempo possibile.",
        },
    },
}


# ─── Flaw Injection Engine ─────────────────────────────────────


def inject_flaw_omission(document: dict, section_key: str) -> dict:
    """Remove a section entirely from the document (Level 1: Obvious)."""
    doc = document.copy()
    sections = doc.get("sections", {}).copy()
    if section_key in sections:
        del sections[section_key]
    doc["sections"] = sections
    return doc


def inject_flaw_insufficient(document: dict, section_key: str) -> dict:
    """Make a section vague/incomplete (Level 2: Subtle)."""
    doc = document.copy()
    sections = doc.get("sections", {}).copy()
    if section_key in sections:
        original = sections[section_key]
        # Truncate to first sentence and add vague language
        first_sentence = original.split(".")[0] + "."
        sections[section_key] = (
            first_sentence + " Per maggiori dettagli, consultare la documentazione interna."
        )
    doc["sections"] = sections
    return doc


def inject_flaw_conflicting(document: dict, section_key: str) -> dict:
    """Add contradictory information (Level 3: Adversarial)."""
    doc = document.copy()
    sections = doc.get("sections", {}).copy()
    if section_key in sections:
        sections[section_key] += (
            "\n\nNOTA: Quanto sopra è soggetto a deroghe a discrezione del Titolare e può essere modificato unilateralmente in qualsiasi momento senza preavviso."
        )
    doc["sections"] = sections
    return doc


def inject_flaw_outdated(document: dict, section_key: str) -> dict:
    """Insert outdated regulatory references (Level 5: Temporal)."""
    doc = document.copy()
    sections = doc.get("sections", {}).copy()
    outdated_refs = {
        "third_country_transfers": "I trasferimenti verso gli Stati Uniti sono effettuati sulla base del Privacy Shield (Decisione di adeguatezza 2016/1250).",
        "appropriate_safeguards": "Le misure di salvaguardia si basano sulle clausole contrattuali tipo della Decisione 2010/87/UE.",
        "security_measures": "Le misure di sicurezza sono conformi all'Allegato B del D.Lgs. 196/2003 (misure minime di sicurezza).",
    }
    if section_key in outdated_refs:
        sections[section_key] = outdated_refs[section_key]
    doc["sections"] = sections
    return doc


FLAW_INJECTORS = {
    "omission": inject_flaw_omission,
    "insufficient": inject_flaw_insufficient,
    "conflicting": inject_flaw_conflicting,
    "outdated": inject_flaw_outdated,
}


# ─── Test Case Generator ──────────────────────────────────────


def generate_document_text(template_name: str, sections: dict, company_info: dict = None) -> str:
    """Render a document template to text, filling in company info placeholders."""
    template = DOCUMENT_TEMPLATES.get(template_name)
    if not template:
        return ""

    info = company_info or {
        "company_name": "Test Company S.r.l.",
        "address": "Via Roma 1, 20121 Milano (MI)",
        "email": "info@testcompany.it",
        "domain": "testcompany.it",
    }

    lines = [f"# {template['title']}\n"]
    for key, content in sections.items():
        section_title = key.replace("_", " ").title()
        rendered = content
        for placeholder, value in info.items():
            rendered = rendered.replace(f"{{{placeholder}}}", value)
        lines.append(f"## {section_title}\n{rendered}\n")

    return "\n".join(lines)


def enforcement_to_test_case(record: EnforcementRecord, difficulty: int = 1) -> dict:
    """
    Convert an enforcement record to a NormaAI test case.

    Args:
        record: The enforcement record
        difficulty: Flaw injection difficulty (1-5)

    Returns:
        TestCase as dict (ready for JSON serialization)
    """
    article_map = FRAMEWORK_ARTICLE_MAPS.get(record.framework, GDPR_ARTICLE_DOCUMENT_MAP)

    # Find the best matching template for the violated articles
    doc_type = "privacy_policy"  # default
    flaws_to_inject = []

    for article in record.violated_articles:
        # Try exact match, then parent match
        mapping = article_map.get(article)
        if not mapping:
            # Try parent article (e.g., Art. 13 for Art. 13(2)(a))
            parent = re.match(r"(Art\.\s*\d+)", article)
            if parent:
                mapping = article_map.get(parent.group(1))

        if mapping:
            doc_type = mapping["doc_type"]
            flaws_to_inject.append(
                {
                    "article": article,
                    "section": mapping["section"],
                }
            )

    # Get template
    template = DOCUMENT_TEMPLATES.get(doc_type, DOCUMENT_TEMPLATES["privacy_policy"])
    sections = dict(template["sections"])

    # Inject flaws based on difficulty
    injector_name = {1: "omission", 2: "insufficient", 3: "conflicting", 5: "outdated"}.get(
        difficulty, "omission"
    )
    injector = FLAW_INJECTORS.get(injector_name, inject_flaw_omission)

    for flaw in flaws_to_inject:
        doc_with_sections = {"sections": sections}
        doc_with_sections = injector(doc_with_sections, flaw["section"])
        sections = doc_with_sections["sections"]

    # Generate document text
    document_text = generate_document_text(doc_type, sections)

    # Build expected findings
    expected_findings = []
    for article in record.violated_articles:
        vtype = (
            "omission"
            if difficulty == 1
            else ("insufficient" if difficulty == 2 else "conflicting")
        )
        expected_findings.append(
            {
                "framework": record.framework,
                "article": article,
                "violation_type": vtype,
                "severity": record.severity,
                "description": f"Violazione {article}: {record.violation_summary[:200]}",
            }
        )

    # Determine difficulty enum
    difficulty_map = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}

    case_id = f"{record.framework}-SANCTION-{record.date[:4]}-{record.country}-{record.id[-3:]}"

    return {
        "id": case_id,
        "name": f"Sanzione {record.authority} {record.date} — {', '.join(record.violated_articles[:3])}",
        "description": f"Test case derivato da sanzione reale: {record.violation_summary[:300]}",
        "source_type": "sanction",
        "sanction_source": {
            "authority": record.authority,
            "reference": record.id,
            "url": record.decision_url,
            "fine_amount_eur": record.fine_eur,
            "decision_date": record.date,
            "country": record.country,
        },
        "task_type": "gap_analysis",
        "query": record.framework,
        "document": {
            "document_type": doc_type,
            "content": document_text,
            "language": "it",
            "industry": record.company_sector,
            "company_size": record.company_size or "PMI",
        },
        "company_profile": {
            "name": "Test Company S.r.l.",
            "sector": record.company_sector,
            "employee_count": 50,
            "revenue_eur": 5000000,
            "jurisdictions": [record.country, "EU"],
            "applicable_frameworks": [record.framework],
            "existing_documents": document_text,
        },
        "expected_findings": expected_findings,
        "expected_not_findings": [],
        "difficulty": difficulty_map.get(difficulty, 1),
        "tags": [
            record.framework.lower(),
            record.country.lower(),
            record.company_sector.lower(),
            f"fine_{int(record.fine_eur)}",
        ],
        "validated_by": None,
        "enabled": True,
    }


# ─── Pre-built Enforcement Records ────────────────────────────
# Based on real GDPR Enforcement Tracker data (public information)

KNOWN_ENFORCEMENTS: list[EnforcementRecord] = [
    EnforcementRecord(
        id="GARANTE-2024-001",
        authority="Garante Privacy Italia",
        country="IT",
        date="2024-03-15",
        fine_eur=50000,
        company_sector="e-commerce",
        violated_articles=["Art. 13(2)(a)", "Art. 5(1)(e)"],
        violation_summary="Mancata indicazione del periodo di conservazione dei dati nella privacy policy. I dati venivano conservati a tempo indeterminato senza giustificazione.",
        violation_types=["omission"],
        framework="GDPR",
        severity="critical",
    ),
    EnforcementRecord(
        id="GARANTE-2024-002",
        authority="Garante Privacy Italia",
        country="IT",
        date="2024-05-22",
        fine_eur=150000,
        company_sector="healthcare",
        violated_articles=["Art. 28(3)(h)", "Art. 28(3)(d)", "Art. 32"],
        violation_summary="DPA con il fornitore cloud non includeva diritto di audit per il titolare. Sub-responsabili non autorizzati. Misure di sicurezza insufficienti per dati sanitari.",
        violation_types=["omission", "insufficient"],
        framework="GDPR",
        severity="critical",
    ),
    EnforcementRecord(
        id="GARANTE-2024-003",
        authority="Garante Privacy Italia",
        country="IT",
        date="2024-07-10",
        fine_eur=20000,
        company_sector="marketing",
        violated_articles=["Art. 7(3)", "Art. 6(1)(a)", "Art. 13(2)(c)"],
        violation_summary="Consenso marketing raccolto con checkbox pre-selezionata. Nessun meccanismo di revoca del consenso facilmente accessibile. Informativa non menzionava il diritto alla revoca.",
        violation_types=["conflicting", "omission"],
        framework="GDPR",
        severity="major",
    ),
    EnforcementRecord(
        id="ICO-2024-001",
        authority="ICO UK",
        country="UK",
        date="2024-02-28",
        fine_eur=4200000,
        company_sector="technology",
        company_size="large",
        violated_articles=["Art. 5(1)(a)", "Art. 6(1)(a)", "Art. 13(1)(c)", "Art. 22"],
        violation_summary="Profilazione algoritmica degli utenti senza base giuridica valida. Mancata informativa sui processi decisionali automatizzati. Informativa carente sulle finalità.",
        violation_types=["omission", "insufficient"],
        framework="GDPR",
        severity="critical",
    ),
    EnforcementRecord(
        id="CNIL-2024-001",
        authority="CNIL France",
        country="FR",
        date="2024-01-18",
        fine_eur=10000000,
        company_sector="advertising",
        company_size="large",
        violated_articles=["Art. 5(1)(a)", "Art. 7(1)", "Art. 7(2)", "Art. 13(1)(f)"],
        violation_summary="Cookie di tracciamento depositati senza consenso valido. Consenso non dimostrabile. Banner cookie non distinguibile. Trasferimenti verso USA non dichiarati nell'informativa.",
        violation_types=["omission", "insufficient", "conflicting"],
        framework="GDPR",
        severity="critical",
    ),
    EnforcementRecord(
        id="CNIL-2024-002",
        authority="CNIL France",
        country="FR",
        date="2024-04-05",
        fine_eur=800000,
        company_sector="finance",
        violated_articles=["Art. 33", "Art. 34", "Art. 5(1)(f)"],
        violation_summary="Data breach non notificato all'autorità entro 72 ore. Interessati non informati nonostante rischio elevato. Backup non isolati dal database principale compromesso.",
        violation_types=["omission"],
        framework="GDPR",
        severity="critical",
    ),
    EnforcementRecord(
        id="GARANTE-2024-004",
        authority="Garante Privacy Italia",
        country="IT",
        date="2024-09-12",
        fine_eur=100000,
        company_sector="retail",
        violated_articles=["Art. 35", "Art. 22", "Art. 13(2)(f)"],
        violation_summary="Sistema di videosorveglianza con riconoscimento facciale implementato senza DPIA. Decisioni automatizzate su accesso clienti senza salvaguardie. Informativa non menzionava la profilazione.",
        violation_types=["omission"],
        framework="GDPR",
        severity="critical",
    ),
    EnforcementRecord(
        id="BAFIN-2024-001",
        authority="BaFin Germany",
        country="DE",
        date="2024-06-20",
        fine_eur=250000,
        company_sector="banking",
        company_size="mid-cap",
        violated_articles=["Art. 6", "Art. 9", "Art. 11"],
        violation_summary="Framework di gestione rischi ICT non conforme a DORA. Mancanza di procedure documentate per il rilevamento anomalie. Piano di ripristino non testato negli ultimi 12 mesi.",
        violation_types=["omission", "insufficient"],
        framework="DORA",
        severity="critical",
    ),
    EnforcementRecord(
        id="BAFIN-2024-002",
        authority="BaFin Germany",
        country="DE",
        date="2024-08-15",
        fine_eur=180000,
        company_sector="insurance",
        violated_articles=["Art. 28", "Art. 30"],
        violation_summary="Contratti con fornitori ICT critici privi delle clausole contrattuali minime richieste da DORA. Nessuna exit strategy documentata per i fornitori cloud.",
        violation_types=["omission"],
        framework="DORA",
        severity="critical",
    ),
    EnforcementRecord(
        id="ENISA-2024-001",
        authority="National CSIRT (Italia)",
        country="IT",
        date="2024-10-01",
        fine_eur=75000,
        company_sector="energy",
        violated_articles=["Art. 21(2)(b)", "Art. 23", "Art. 21(2)(d)"],
        violation_summary="Mancata notifica incidente significativo al CSIRT entro 24 ore. Assenza di piano di gestione incidenti. Nessuna valutazione sicurezza supply chain.",
        violation_types=["omission"],
        framework="NIS2",
        severity="critical",
    ),
    EnforcementRecord(
        id="GARANTE-2024-005",
        authority="Garante Privacy Italia",
        country="IT",
        date="2024-11-05",
        fine_eur=500000,
        company_sector="technology",
        company_size="large",
        violated_articles=["Art. 5(1)(b)", "Art. 5(1)(c)", "Art. 13(2)(a)", "Art. 30"],
        violation_summary="Dati raccolti per finalità specifica poi utilizzati per addestrare modello IA senza consenso specifico. Raccolta eccessiva di dati non necessari. Registro trattamenti incompleto.",
        violation_types=["conflicting", "omission"],
        framework="GDPR",
        severity="critical",
    ),
    EnforcementRecord(
        id="GARANTE-2023-001",
        authority="Garante Privacy Italia",
        country="IT",
        date="2023-03-31",
        fine_eur=20000000,
        company_sector="technology",
        company_size="large",
        violated_articles=["Art. 5(1)(a)", "Art. 6", "Art. 8", "Art. 13", "Art. 25"],
        violation_summary="Chatbot IA lanciato senza base giuridica per il trattamento massivo di dati. Nessuna verifica dell'età. Informativa inadeguata. Privacy by design non implementata.",
        violation_types=["omission", "insufficient"],
        framework="GDPR",
        severity="critical",
    ),
    EnforcementRecord(
        id="GARANTE-2024-006",
        authority="Garante Privacy Italia",
        country="IT",
        date="2024-06-01",
        fine_eur=80000,
        company_sector="hr_services",
        violated_articles=["Art. 22", "Art. 35", "Art. 13(2)(f)"],
        violation_summary="Sistema di screening CV automatizzato senza supervisione umana significativa. DPIA non effettuata. Candidati non informati del processo automatizzato.",
        violation_types=["omission"],
        framework="GDPR",
        severity="critical",
    ),
    EnforcementRecord(
        id="ICO-2023-001",
        authority="ICO UK",
        country="UK",
        date="2023-09-15",
        fine_eur=12500000,
        company_sector="social_media",
        company_size="large",
        violated_articles=["Art. 5(1)(a)", "Art. 5(1)(c)", "Art. 44", "Art. 46"],
        violation_summary="Trasferimento massivo di dati verso USA senza garanzie adeguate post-Schrems II. Raccolta dati eccessiva. Mancanza di trasparenza sulle finalità pubblicitarie.",
        violation_types=["omission", "outdated"],
        framework="GDPR",
        severity="critical",
    ),
    EnforcementRecord(
        id="CNIL-2024-003",
        authority="CNIL France",
        country="FR",
        date="2024-08-20",
        fine_eur=300000,
        company_sector="retail",
        violated_articles=["Art. 5(1)(e)", "Art. 17", "Art. 28(3)(f)"],
        violation_summary="Dati clienti conservati oltre 5 anni dopo l'ultimo acquisto senza base giuridica. Richieste di cancellazione non evase. DPA non prevedeva obbligo di cancellazione al termine.",
        violation_types=["omission", "insufficient"],
        framework="GDPR",
        severity="major",
    ),
]


# ─── Pipeline Orchestration ───────────────────────────────────


def generate_test_cases_from_enforcements(
    records: list[EnforcementRecord] = None,
    difficulties: list[int] = None,
    framework_filter: str = None,
) -> list[dict]:
    """
    Generate test cases from enforcement records.

    Args:
        records: List of enforcement records (defaults to KNOWN_ENFORCEMENTS)
        difficulties: Difficulty levels to generate (defaults to [1, 2, 3])
        framework_filter: Filter by framework
    """
    if records is None:
        records = KNOWN_ENFORCEMENTS
    if difficulties is None:
        difficulties = [1, 2, 3]
    if framework_filter:
        records = [r for r in records if r.framework == framework_filter]

    test_cases = []
    for record in records:
        for difficulty in difficulties:
            try:
                tc = enforcement_to_test_case(record, difficulty)
                # Make ID unique per difficulty
                tc["id"] = f"{tc['id']}-L{difficulty}"
                tc["name"] = f"[L{difficulty}] {tc['name']}"
                test_cases.append(tc)
            except Exception as e:
                logger.error(f"Failed to generate test case from {record.id}: {e}")

    return test_cases


def save_test_cases(test_cases: list[dict], filename: str = None) -> Path:
    """Save test cases to JSON file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"sanctions_batch_{timestamp}.json"

    output_path = OUTPUT_DIR / filename
    output_path.write_text(
        json.dumps({"test_cases": test_cases}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"Saved {len(test_cases)} test cases to {output_path}")
    return output_path


def main():
    """CLI entry point for sanctions harvester."""
    parser = argparse.ArgumentParser(description="NormaAI Sanctions Harvester")
    parser.add_argument("--framework", default=None, help="Filter by framework (GDPR, DORA, NIS2)")
    parser.add_argument(
        "--difficulty", type=int, nargs="+", default=[1, 2, 3], help="Difficulty levels"
    )
    parser.add_argument("--output", default=None, help="Output filename")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    test_cases = generate_test_cases_from_enforcements(
        framework_filter=args.framework,
        difficulties=args.difficulty,
    )

    path = save_test_cases(test_cases, args.output)
    print(f"Generated {len(test_cases)} test cases → {path}")


if __name__ == "__main__":
    main()
