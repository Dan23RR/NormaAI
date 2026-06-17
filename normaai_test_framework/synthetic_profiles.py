"""
NormaAI Validation Framework - Synthetic Company Profiles
==========================================================
5 profili aziendali fittizi con gap di compliance noti e documentati.
Ogni profilo include:
- Descrizione aziendale dettagliata
- Framework target per il test
- Gap intenzionalmente "iniettati" con il riferimento normativo esatto
- Livello di difficoltà (EASY / MEDIUM / HARD)

I gap sono basati su sanzioni reali e scenari documentati.
"""

SYNTHETIC_PROFILES = [
    # ═══════════════════════════════════════════════════════════════
    # PROFILO A: Manifatturiero tedesco - CSDDD + CSRD
    # Gap ispirati alla sanzione CSDDD-type (catena di fornitura)
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "SYNTH-A",
        "company_name": "StahlWerk Industries GmbH",
        "description": (
            "StahlWerk Industries GmbH is a German manufacturing company headquartered in "
            "Düsseldorf, specializing in automotive steel components. The company has 1,200 "
            "employees across 3 EU facilities (Germany, Poland, Czech Republic) and an annual "
            "turnover of EUR 380 million. StahlWerk sources raw materials from 47 tier-1 "
            "suppliers, including 12 suppliers in Turkey, India, and Brazil. "
            "\n\n"
            "The company has a basic Code of Conduct for suppliers but does NOT conduct any "
            "on-site audits or human rights due diligence on its supply chain beyond tier-1. "
            "There is no formal grievance mechanism for workers in the supply chain to report "
            "violations. StahlWerk publishes an annual sustainability report but it only covers "
            "Scope 1 and Scope 2 emissions - Scope 3 (supply chain) emissions are not reported "
            "at all. The report uses GRI standards but has NOT been aligned with ESRS yet. "
            "The company has not conducted a double materiality assessment. "
            "\n\n"
            "StahlWerk uses an internal ERP system that collects some environmental data from "
            "its own facilities but has no system to collect ESG data from suppliers. The board "
            "has no dedicated sustainability committee - ESG is handled by the CFO part-time."
        ),
        "sector": "Manufacturing - Automotive Components",
        "employees": 1200,
        "turnover_eur": 380_000_000,
        "jurisdictions": ["DE", "PL", "CZ"],
        "test_cases": [
            {
                "framework": "CSDDD",
                "test_id": "A-CSDDD-01",
                "injected_gap": "No human rights due diligence beyond tier-1 suppliers",
                "expected_article": "Art. 7-8 CSDDD (Directive 2024/1760)",
                "severity": "NON_COMPLIANT",
                "difficulty": "EASY",
                "description": (
                    "CSDDD Art. 7 requires companies to identify and assess actual and potential "
                    "adverse human rights and environmental impacts in their own operations AND "
                    "those of their subsidiaries and business partners throughout the chain of "
                    "activities. StahlWerk only checks tier-1, ignoring tier-2+ where most "
                    "forced labor and environmental damage occurs (mining, smelting)."
                )
            },
            {
                "framework": "CSDDD",
                "test_id": "A-CSDDD-02",
                "injected_gap": "No grievance mechanism for supply chain workers",
                "expected_article": "Art. 14 CSDDD (Directive 2024/1760)",
                "severity": "NON_COMPLIANT",
                "difficulty": "EASY",
                "description": (
                    "CSDDD Art. 14 requires companies to establish and maintain a complaints "
                    "procedure (grievance mechanism) that allows persons and organisations to "
                    "submit complaints regarding adverse impacts. StahlWerk has no such mechanism."
                )
            },
            {
                "framework": "CSRD",
                "test_id": "A-CSRD-01",
                "injected_gap": "No Scope 3 emissions reporting",
                "expected_article": "ESRS E1-6 (Climate Change - GHG Emissions)",
                "severity": "NON_COMPLIANT",
                "difficulty": "EASY",
                "description": (
                    "ESRS E1-6 requires disclosure of Scope 1, 2, AND 3 GHG emissions. For a "
                    "manufacturing company with a significant supply chain, Scope 3 typically "
                    "represents 70-90% of total emissions. Omitting it entirely is a major gap."
                )
            },
            {
                "framework": "CSRD",
                "test_id": "A-CSRD-02",
                "injected_gap": "No double materiality assessment conducted",
                "expected_article": "ESRS 1 Chapter 3 (Double Materiality)",
                "severity": "NON_COMPLIANT",
                "difficulty": "MEDIUM",
                "description": (
                    "ESRS 1 requires a double materiality assessment covering both impact "
                    "materiality (company's impact on people/environment) and financial "
                    "materiality (sustainability issues affecting the company). StahlWerk has "
                    "not performed this assessment, which is the foundation of CSRD reporting."
                )
            },
        ]
    },

    # ═══════════════════════════════════════════════════════════════
    # PROFILO B: SaaS francese - AI Act + GDPR
    # Gap ispirati a sanzioni reali CNIL e scenari AI Act
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "SYNTH-B",
        "company_name": "VisionGuard SAS",
        "description": (
            "VisionGuard SAS is a French B2B SaaS company based in Lyon with 85 employees "
            "and EUR 12 million annual revenue. The company develops an AI-powered workplace "
            "safety monitoring system that uses CCTV cameras with real-time computer vision "
            "to detect PPE compliance (helmets, gloves, safety vests) in industrial facilities. "
            "\n\n"
            "The system uses biometric categorization to identify individual workers by their "
            "gait patterns and body measurements to track PPE compliance per employee. This "
            "biometric processing is NOT disclosed in the employee privacy notice. Workers are "
            "informed that 'cameras monitor safety compliance' but NOT that individual biometric "
            "profiles are created and stored. Consent is collected via a clause buried in the "
            "employment contract (not separate, not freely given). "
            "\n\n"
            "The AI model was trained on a dataset of 50,000 images collected from client "
            "facilities. No AI impact assessment has been conducted. There is no human oversight "
            "mechanism - the system automatically generates compliance reports and can trigger "
            "disciplinary alerts to HR without human review. Model accuracy is 94.2% overall "
            "but drops to 87.1% for workers wearing non-standard PPE or with mobility aids. "
            "No bias testing has been performed. The system has no technical documentation "
            "as required by the AI Act. Data is processed on AWS eu-west-1 servers but "
            "telemetry data is sent to a US-based analytics provider without SCCs."
        ),
        "sector": "Technology - AI/Computer Vision SaaS",
        "employees": 85,
        "turnover_eur": 12_000_000,
        "jurisdictions": ["FR"],
        "test_cases": [
            {
                "framework": "AI_ACT",
                "test_id": "B-AIACT-01",
                "injected_gap": "Biometric categorization system without AI Act compliance",
                "expected_article": "Art. 6(2) + Annex III(1) AI Act (Reg. 2024/1689)",
                "severity": "NON_COMPLIANT",
                "difficulty": "MEDIUM",
                "description": (
                    "The AI Act classifies biometric categorization systems used in workplaces "
                    "as HIGH-RISK (Annex III, point 1). VisionGuard uses gait/body biometrics "
                    "to identify individuals, which triggers full Chapter 3 obligations: "
                    "risk management system, data governance, technical documentation, "
                    "human oversight, accuracy/robustness requirements."
                )
            },
            {
                "framework": "AI_ACT",
                "test_id": "B-AIACT-02",
                "injected_gap": "No AI impact assessment or technical documentation",
                "expected_article": "Art. 9, 11, 13 AI Act (Reg. 2024/1689)",
                "severity": "NON_COMPLIANT",
                "difficulty": "EASY",
                "description": (
                    "Art. 9 requires a risk management system. Art. 11 requires technical "
                    "documentation. Art. 13 requires transparency. None of these exist."
                )
            },
            {
                "framework": "AI_ACT",
                "test_id": "B-AIACT-03",
                "injected_gap": "No human oversight on automated disciplinary decisions",
                "expected_article": "Art. 14 AI Act (Reg. 2024/1689)",
                "severity": "NON_COMPLIANT",
                "difficulty": "MEDIUM",
                "description": (
                    "Art. 14 requires human oversight for high-risk AI systems. The system "
                    "automatically triggers HR disciplinary alerts without human review, "
                    "violating the requirement for meaningful human control."
                )
            },
            {
                "framework": "GDPR",
                "test_id": "B-GDPR-01",
                "injected_gap": "Biometric data processing without valid consent (Art. 9)",
                "expected_article": "Art. 9(2)(a) GDPR + Art. 7 (Conditions for consent)",
                "severity": "NON_COMPLIANT",
                "difficulty": "EASY",
                "description": (
                    "Biometric data is special category data under Art. 9 GDPR. Processing "
                    "requires explicit consent that is freely given, specific, informed. "
                    "Consent buried in an employment contract is NOT freely given (power "
                    "imbalance) per EDPB Guidelines 05/2020, and workers are not informed "
                    "about biometric profiling."
                )
            },
            {
                "framework": "GDPR",
                "test_id": "B-GDPR-02",
                "injected_gap": "Data transfer to US without adequate safeguards (SCCs)",
                "expected_article": "Art. 46 GDPR (Transfers subject to appropriate safeguards)",
                "severity": "NON_COMPLIANT",
                "difficulty": "EASY",
                "description": (
                    "Telemetry data sent to a US analytics provider without Standard "
                    "Contractual Clauses (SCCs) or other Art. 46 safeguards. Post-Schrems II, "
                    "this is a clear violation."
                )
            },
        ]
    },

    # ═══════════════════════════════════════════════════════════════
    # PROFILO C: Banca italiana - DORA + NIS2 + GDPR
    # Gap ispirati alle sanzioni Banca d'Italia e Garante Privacy
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "SYNTH-C",
        "company_name": "Banca Credito Adriatico S.p.A.",
        "description": (
            "Banca Credito Adriatico S.p.A. is a mid-sized Italian bank headquartered in "
            "Ancona with 2,800 employees, serving 450,000 retail customers and 12,000 SME "
            "clients. Total assets: EUR 18 billion. The bank operates 120 branches across "
            "central Italy and provides standard retail banking, corporate lending, and a "
            "mobile banking app (launched 2022). "
            "\n\n"
            "ICT infrastructure: The bank runs its core banking system on an on-premise IBM "
            "mainframe (legacy, installed 2008). The mobile app and web portal run on a "
            "private cloud hosted by a single Italian provider (no redundancy agreement). "
            "There is NO formal ICT risk management framework - risk assessment is done "
            "annually by the internal audit team using spreadsheets. The bank has never "
            "conducted a digital operational resilience test or threat-led penetration test "
            "(TLPT). Third-party ICT provider contracts do NOT include audit rights, incident "
            "notification obligations, or exit strategies. "
            "\n\n"
            "Cybersecurity: The bank experienced a ransomware incident in March 2025 that "
            "encrypted 30% of branch workstations. The incident was detected after 72 hours. "
            "No incident report was filed with the competent authority within the 24-hour "
            "initial notification window. The bank does not have a dedicated CISO - security "
            "is handled by the IT Operations Manager. There is no formal incident response "
            "plan. Backup tapes are stored in the same building as the primary data center. "
            "\n\n"
            "Data protection: Customer data breach notifications were sent 15 days after the "
            "ransomware incident (exceeding the 72-hour requirement). The bank has a DPO "
            "but the DPO also serves as Head of Legal (conflict of interest)."
        ),
        "sector": "Financial Services - Retail Banking",
        "employees": 2800,
        "turnover_eur": 850_000_000,
        "jurisdictions": ["IT"],
        "test_cases": [
            {
                "framework": "DORA",
                "test_id": "C-DORA-01",
                "injected_gap": "No ICT risk management framework",
                "expected_article": "Art. 6-7 DORA (Reg. 2022/2554)",
                "severity": "NON_COMPLIANT",
                "difficulty": "EASY",
                "description": (
                    "DORA Art. 6 requires financial entities to have a comprehensive ICT risk "
                    "management framework that is documented, reviewed annually, and approved "
                    "by the management body. Using spreadsheets for annual audit does NOT meet "
                    "the DORA standard for a formal, documented ICT risk management framework."
                )
            },
            {
                "framework": "DORA",
                "test_id": "C-DORA-02",
                "injected_gap": "No digital operational resilience testing (TLPT)",
                "expected_article": "Art. 24-27 DORA (Reg. 2022/2554)",
                "severity": "NON_COMPLIANT",
                "difficulty": "MEDIUM",
                "description": (
                    "DORA Art. 26 requires significant financial entities to carry out "
                    "threat-led penetration testing (TLPT) at least every 3 years. The bank "
                    "has never conducted any TLPT."
                )
            },
            {
                "framework": "DORA",
                "test_id": "C-DORA-03",
                "injected_gap": "Third-party ICT contracts lack DORA-required provisions",
                "expected_article": "Art. 30 DORA (Reg. 2022/2554)",
                "severity": "NON_COMPLIANT",
                "difficulty": "MEDIUM",
                "description": (
                    "DORA Art. 30 mandates specific contractual provisions with ICT third-party "
                    "providers including: audit rights, incident notification obligations, "
                    "exit strategies, and data location requirements. None are present."
                )
            },
            {
                "framework": "NIS2",
                "test_id": "C-NIS2-01",
                "injected_gap": "Incident notification exceeded 24-hour window",
                "expected_article": "Art. 23 NIS2 (Directive 2022/2555)",
                "severity": "NON_COMPLIANT",
                "difficulty": "EASY",
                "description": (
                    "NIS2 Art. 23 requires an early warning within 24 hours and an incident "
                    "notification within 72 hours. The bank detected the ransomware after 72h "
                    "and never filed the 24h early warning."
                )
            },
            {
                "framework": "GDPR",
                "test_id": "C-GDPR-01",
                "injected_gap": "Data breach notification exceeded 72 hours",
                "expected_article": "Art. 33 GDPR (Notification to supervisory authority)",
                "severity": "NON_COMPLIANT",
                "difficulty": "EASY",
                "description": (
                    "GDPR Art. 33 requires notification to the supervisory authority within "
                    "72 hours of becoming aware of a personal data breach. The bank notified "
                    "after 15 days - a clear and serious violation."
                )
            },
            {
                "framework": "GDPR",
                "test_id": "C-GDPR-02",
                "injected_gap": "DPO has conflict of interest (also Head of Legal)",
                "expected_article": "Art. 38(6) GDPR (Position of the DPO)",
                "severity": "PARTIALLY_COMPLIANT",
                "difficulty": "HARD",
                "description": (
                    "Art. 38(6) allows the DPO to fulfil other tasks but these must not result "
                    "in a conflict of interest. EDPB Guidelines on DPOs state that Head of Legal "
                    "involves determining purposes of processing, creating a conflict. This is "
                    "a subtle gap that requires knowledge of EDPB guidance."
                )
            },
        ]
    },

    # ═══════════════════════════════════════════════════════════════
    # PROFILO D: Utility olandese - EU Taxonomy + CSRD
    # Gap ispirati a greenwashing reale nei report di sostenibilità
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "SYNTH-D",
        "company_name": "GreenGrid Energy B.V.",
        "description": (
            "GreenGrid Energy B.V. is a Dutch energy utility headquartered in Rotterdam with "
            "4,500 employees and EUR 2.1 billion annual revenue. The company operates a mix "
            "of renewable (60% - wind and solar farms) and natural gas (40%) power generation "
            "assets across the Netherlands and Belgium. "
            "\n\n"
            "In its 2024 sustainability report, GreenGrid claims to be 'Taxonomy-aligned' for "
            "85% of its revenue. However, this calculation includes natural gas activities "
            "classified under the Complementary Delegated Act (CDA) without verifying that "
            "these activities meet the specific technical screening criteria: the gas plants "
            "exceed the 270g CO2e/kWh lifecycle emissions threshold for new installations and "
            "do NOT have binding commitments to switch to renewable or low-carbon gases by 2035. "
            "The company also claims its wind farms are Taxonomy-aligned but has NOT conducted "
            "the mandatory DNSH (Do No Significant Harm) assessment for biodiversity impacts "
            "on marine ecosystems for its offshore installations. "
            "\n\n"
            "CSRD reporting: GreenGrid uses ESRS but has disclosed climate transition targets "
            "without specifying interim milestones (only a 2050 net-zero target, no 2030 "
            "intermediate target as required). The report does not include a CAPEX plan aligned "
            "with the transition targets. The board sustainability committee meets quarterly "
            "but minutes are not published and there is no disclosure of how sustainability "
            "performance is linked to executive remuneration."
        ),
        "sector": "Energy - Power Generation & Utilities",
        "employees": 4500,
        "turnover_eur": 2_100_000_000,
        "jurisdictions": ["NL", "BE"],
        "test_cases": [
            {
                "framework": "TAXONOMY",
                "test_id": "D-TAX-01",
                "injected_gap": "Gas activities claimed as Taxonomy-aligned without meeting TSC",
                "expected_article": "Art. 3 Taxonomy Reg. (2020/852) + CDA TSC (270g threshold)",
                "severity": "NON_COMPLIANT",
                "difficulty": "HARD",
                "description": (
                    "The Taxonomy Regulation Art. 3 requires activities to meet Technical "
                    "Screening Criteria (TSC). Gas plants exceeding 270g CO2e/kWh and lacking "
                    "binding fuel-switch commitments by 2035 cannot be classified as aligned. "
                    "Claiming 85% alignment including non-compliant gas is greenwashing."
                )
            },
            {
                "framework": "TAXONOMY",
                "test_id": "D-TAX-02",
                "injected_gap": "No DNSH assessment for biodiversity on offshore wind",
                "expected_article": "Art. 17 Taxonomy Reg. (2020/852) - DNSH criteria",
                "severity": "NON_COMPLIANT",
                "difficulty": "HARD",
                "description": (
                    "Art. 17 defines Do No Significant Harm. Offshore wind must assess impact "
                    "on biodiversity. Without a DNSH assessment, the activity cannot be claimed "
                    "as Taxonomy-aligned even if it meets the substantial contribution criteria."
                )
            },
            {
                "framework": "CSRD",
                "test_id": "D-CSRD-01",
                "injected_gap": "No interim climate targets (only 2050, missing 2030)",
                "expected_article": "ESRS E1-4 (Targets related to climate change mitigation)",
                "severity": "PARTIALLY_COMPLIANT",
                "difficulty": "MEDIUM",
                "description": (
                    "ESRS E1-4 requires disclosure of targets related to climate change "
                    "mitigation and adaptation, including interim targets. A 2050-only target "
                    "without 2030 milestones is insufficient."
                )
            },
            {
                "framework": "CSRD",
                "test_id": "D-CSRD-02",
                "injected_gap": "No Taxonomy-aligned CAPEX plan disclosed",
                "expected_article": "ESRS E1-7 (Expected financial effects) + Art. 8 Taxonomy Reg.",
                "severity": "NON_COMPLIANT",
                "difficulty": "HARD",
                "description": (
                    "ESRS E1-7 requires disclosure of expected financial effects of climate "
                    "risks and transition plan. Art. 8 of the Taxonomy Regulation requires "
                    "disclosure of the proportion of CAPEX aligned with Taxonomy objectives."
                )
            },
        ]
    },

    # ═══════════════════════════════════════════════════════════════
    # PROFILO E: Scale-up spagnola - GDPR (DPA errors) + AI Act
    # Gap ispirati a sanzione AEPD e scenari AI Act
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "SYNTH-E",
        "company_name": "TalentLens AI S.L.",
        "description": (
            "TalentLens AI S.L. is a Spanish HR-tech startup based in Barcelona with 45 "
            "employees and EUR 3.5 million annual revenue. The company provides an AI-powered "
            "recruitment screening platform that analyzes candidate CVs, video interviews "
            "(facial expression analysis and voice tone), and social media profiles to generate "
            "a 'Candidate Fit Score' used by HR departments to shortlist applicants. "
            "\n\n"
            "The platform processes approximately 200,000 candidate profiles per year for 150 "
            "enterprise clients across Spain, France, and Germany. The AI model was trained on "
            "historical hiring data from 2018-2023, which has not been audited for bias. "
            "Internal testing shows the system scores female candidates 12% lower on average "
            "for technical roles and candidates over 50 are 23% less likely to be shortlisted. "
            "No bias mitigation measures have been implemented. "
            "\n\n"
            "Data Processing Agreement with clients: TalentLens acts as a data processor. "
            "The DPA template does NOT include the right of audit by the controller (client), "
            "does NOT specify sub-processors, and states data will be retained indefinitely "
            "for 'model improvement purposes.' Candidates are not informed their video "
            "interviews are analyzed by AI for emotional recognition. The privacy policy "
            "mentions 'automated processing' but does not disclose the specific logic involved "
            "or the right to contest automated decisions. There is no Data Protection Impact "
            "Assessment (DPIA) despite high-risk processing of special category data."
        ),
        "sector": "Technology - HR-Tech / AI Recruitment",
        "employees": 45,
        "turnover_eur": 3_500_000,
        "jurisdictions": ["ES", "FR", "DE"],
        "test_cases": [
            {
                "framework": "AI_ACT",
                "test_id": "E-AIACT-01",
                "injected_gap": "Emotion recognition in recruitment without compliance",
                "expected_article": "Art. 5(1)(f) AI Act - Prohibited practices (emotion recognition in workplace)",
                "severity": "NON_COMPLIANT",
                "difficulty": "MEDIUM",
                "description": (
                    "The AI Act Art. 5(1)(f) PROHIBITS AI systems that infer emotions of a "
                    "natural person in the workplace, except for medical or safety reasons. "
                    "Facial expression and voice tone analysis in recruitment is a PROHIBITED "
                    "practice, not just high-risk - this is the most severe category."
                )
            },
            {
                "framework": "AI_ACT",
                "test_id": "E-AIACT-02",
                "injected_gap": "AI recruitment system with documented bias not mitigated",
                "expected_article": "Art. 10 AI Act (Data and data governance) + Annex III(4)",
                "severity": "NON_COMPLIANT",
                "difficulty": "MEDIUM",
                "description": (
                    "AI recruitment systems are HIGH-RISK under Annex III(4). Art. 10 requires "
                    "training data to be examined for possible biases. Known gender and age bias "
                    "(12% and 23% respectively) without mitigation is a clear violation."
                )
            },
            {
                "framework": "GDPR",
                "test_id": "E-GDPR-01",
                "injected_gap": "DPA missing audit rights for data controller",
                "expected_article": "Art. 28(3)(h) GDPR (Processor obligations)",
                "severity": "NON_COMPLIANT",
                "difficulty": "EASY",
                "description": (
                    "Art. 28(3)(h) explicitly requires the processor to make available all "
                    "information necessary to demonstrate compliance and allow for audits. "
                    "This is one of the most commonly sanctioned DPA deficiencies."
                )
            },
            {
                "framework": "GDPR",
                "test_id": "E-GDPR-02",
                "injected_gap": "Indefinite data retention for model training",
                "expected_article": "Art. 5(1)(e) GDPR (Storage limitation) + Art. 28(3)(g)",
                "severity": "NON_COMPLIANT",
                "difficulty": "EASY",
                "description": (
                    "Art. 5(1)(e) requires data to be kept for no longer than necessary. "
                    "Art. 28(3)(g) requires the processor to delete or return data after "
                    "the end of the service. Indefinite retention for model training violates both."
                )
            },
            {
                "framework": "GDPR",
                "test_id": "E-GDPR-03",
                "injected_gap": "No DPIA for high-risk automated profiling",
                "expected_article": "Art. 35 GDPR (Data protection impact assessment)",
                "severity": "NON_COMPLIANT",
                "difficulty": "EASY",
                "description": (
                    "Art. 35 requires a DPIA when processing is likely to result in a high risk, "
                    "especially for systematic and extensive profiling with legal effects. "
                    "AI-based recruitment screening is explicitly listed as requiring DPIA."
                )
            },
            {
                "framework": "GDPR",
                "test_id": "E-GDPR-04",
                "injected_gap": "No disclosure of automated decision-making logic or right to contest",
                "expected_article": "Art. 22 GDPR + Art. 13(2)(f) GDPR",
                "severity": "NON_COMPLIANT",
                "difficulty": "MEDIUM",
                "description": (
                    "Art. 22 gives data subjects the right not to be subject to solely automated "
                    "decisions with legal effects. Art. 13(2)(f) requires disclosure of the "
                    "existence of automated decision-making, meaningful information about the "
                    "logic involved, and the significance and envisaged consequences."
                )
            },
        ]
    },
]


# ─── Utility functions ───────────────────────────────

def get_all_test_cases():
    """Returns a flat list of all test cases across all profiles."""
    cases = []
    for profile in SYNTHETIC_PROFILES:
        for tc in profile["test_cases"]:
            cases.append({
                "profile_id": profile["id"],
                "company_name": profile["company_name"],
                **tc
            })
    return cases


def get_profile_by_id(profile_id):
    """Returns a profile by its ID."""
    for p in SYNTHETIC_PROFILES:
        if p["id"] == profile_id:
            return p
    return None


def summary():
    """Prints a summary of all profiles and test cases."""
    total = 0
    for p in SYNTHETIC_PROFILES:
        n = len(p["test_cases"])
        total += n
        fw_set = sorted(set(tc["framework"] for tc in p["test_cases"]))
        print(f"  {p['id']}: {p['company_name']} - {n} test cases ({', '.join(fw_set)})")
    print(f"\n  TOTALE: {total} test cases across {len(SYNTHETIC_PROFILES)} profiles")


if __name__ == "__main__":
    print("=" * 60)
    print("NormaAI Validation Framework - Synthetic Profiles Summary")
    print("=" * 60)
    summary()
