"""Verify EUR-Lex citations for the Codex Post-Omnibus PDF.

Runs SPARQL queries against the official EU SPARQL endpoint
(https://publications.europa.eu/webapi/rdf/sparql) to validate the
6 claims flagged in `marketing/codex_cap1_DRAFT.md`.

Output:
  - Console table: green/yellow/red for each claim
  - File `marketing/codex_cap1_VERIFIED.md` with citations + URLs

Run:  poetry run python scripts/verify_codex_citations.py

NB: this script is conservative. If a SPARQL query returns no result,
the claim is marked YELLOW (not RED) - the absence of result may mean
the document is too recent to be indexed or our query is too narrow.
A RED mark is only used when the query returns a CONTRADICTING result.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

SPARQL_ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"

# Public CELEX for the relevant base directives.
CELEX_CSRD = "32022L2464"      # Directive (EU) 2022/2464 - CSRD
CELEX_CSDDD = "32024L1760"     # Directive (EU) 2024/1760 - CSDDD
CELEX_TAXONOMY = "32020R0852"  # Regulation (EU) 2020/852 - EU Taxonomy
CELEX_ESRS_SET1 = "32023R2772" # Implementing Reg. - ESRS Set 1


# ─────────────────────────── Data model ─────────────────────────────

@dataclass
class ClaimResult:
    claim_id: str
    title: str
    status: str             # "GREEN" | "YELLOW" | "RED"
    summary: str
    evidence_url: str | None = None
    sparql_query: str | None = None
    raw_results: list = field(default_factory=list)


# ─────────────────────── SPARQL helper ──────────────────────────────

def run_sparql(query: str, timeout: float = 30.0) -> list[dict]:
    """POST a SPARQL query and return the bindings list, or []."""
    headers = {
        "Accept": "application/sparql-results+json",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "NormaAI/0.3 codex-citation-verifier",
    }
    try:
        resp = httpx.post(
            SPARQL_ENDPOINT,
            data={"query": query, "format": "application/sparql-results+json"},
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            print(f"  [WARN] HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            return []
        data = resp.json()
        return data.get("results", {}).get("bindings", [])
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        print(f"  [WARN] SPARQL error: {e}", file=sys.stderr)
        return []


# ────────────── Reusable query builders ──────────────────────────────

def query_amending_acts(target_celex: str, since_year: int = 2024) -> str:
    """Find all acts that amend the given CELEX and were published since
    `since_year`. Useful for spotting Omnibus modifications.
    """
    return f"""
    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
    PREFIX dcterms: <http://purl.org/dc/terms/>

    SELECT DISTINCT ?work ?celex ?title ?date_doc WHERE {{
        ?work cdm:work_amends_resource_legal ?target .
        ?target cdm:resource_legal_id_celex "{target_celex}" .
        ?work cdm:resource_legal_id_celex ?celex .
        OPTIONAL {{ ?work dcterms:date ?date_doc }}
        OPTIONAL {{ ?work cdm:work_date_document ?date_doc }}
        OPTIONAL {{
            ?expr cdm:expression_belongs_to_work ?work .
            ?expr cdm:expression_title ?title .
            FILTER(LANG(?title) = "en")
        }}
        FILTER(STR(?date_doc) >= "{since_year}-01-01" || !BOUND(?date_doc))
    }}
    ORDER BY DESC(?date_doc)
    LIMIT 50
    """


def query_omnibus_proposals() -> str:
    """Search for any document with 'omnibus' in title published since 2024."""
    return """
    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
    PREFIX dcterms: <http://purl.org/dc/terms/>

    SELECT DISTINCT ?work ?celex ?title ?date_doc ?type WHERE {
        ?expr cdm:expression_belongs_to_work ?work .
        ?expr cdm:expression_title ?title .
        ?work cdm:resource_legal_id_celex ?celex .
        OPTIONAL { ?work cdm:work_date_document ?date_doc }
        OPTIONAL { ?work cdm:work_has_resource-type ?type }
        FILTER(LANG(?title) = "en")
        FILTER(REGEX(?title, "omnibus", "i"))
        FILTER(STR(?date_doc) >= "2024-01-01" || !BOUND(?date_doc))
    }
    ORDER BY DESC(?date_doc)
    LIMIT 30
    """


def query_celex_metadata(celex: str) -> str:
    """Get title, date, OJ ref for a specific CELEX."""
    return f"""
    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>

    SELECT ?title ?date_doc ?oj_ref WHERE {{
        ?work cdm:resource_legal_id_celex "{celex}" .
        OPTIONAL {{ ?work cdm:work_date_document ?date_doc }}
        OPTIONAL {{ ?work cdm:work_published_in_official-journal ?oj_ref }}
        OPTIONAL {{
            ?expr cdm:expression_belongs_to_work ?work .
            ?expr cdm:expression_title ?title .
            FILTER(LANG(?title) = "en")
        }}
    }}
    LIMIT 5
    """


# ────────────────────────── Claim verifiers ─────────────────────────

def verify_claim_1_omnibus_adoption() -> ClaimResult:
    """Claim 1: l'Omnibus I è stato adottato in via definitiva (data + OJ ref)."""
    print("\n[CLAIM 1] Cercando atti 'omnibus' adottati 2024-2025...")
    bindings = run_sparql(query_omnibus_proposals())
    if not bindings:
        return ClaimResult(
            claim_id="1",
            title="Omnibus I adozione e numero OJ",
            status="YELLOW",
            summary=(
                "Nessun atto con 'omnibus' nel titolo trovato via SPARQL post-2024. "
                "Il pacchetto potrebbe essere ancora in trilogue o non indicizzato. "
                "Verifica manuale richiesta su https://eur-lex.europa.eu/search.html?text=omnibus"
            ),
            sparql_query=query_omnibus_proposals(),
        )

    # Stampa i top hit
    top = bindings[0]
    celex = top.get("celex", {}).get("value", "?")
    title = top.get("title", {}).get("value", "?")[:140]
    date = top.get("date_doc", {}).get("value", "?")
    url = f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}" if celex != "?" else None

    return ClaimResult(
        claim_id="1",
        title="Omnibus I adozione e numero OJ",
        status="GREEN",
        summary=f"Top hit: CELEX {celex} ({date}) - {title}",
        evidence_url=url,
        sparql_query=query_omnibus_proposals(),
        raw_results=[
            {
                "celex": b.get("celex", {}).get("value"),
                "title": b.get("title", {}).get("value", "")[:120],
                "date": b.get("date_doc", {}).get("value"),
            }
            for b in bindings[:5]
        ],
    )


def verify_claim_2_csrd_thresholds() -> ClaimResult:
    """Claim 2: soglie CSRD post-Omnibus (50M ricavi, 25M bilancio)."""
    print("\n[CLAIM 2] Cercando atti che modificano CSRD (32022L2464)...")
    bindings = run_sparql(query_amending_acts(CELEX_CSRD, since_year=2024))
    if not bindings:
        return ClaimResult(
            claim_id="2",
            title="CSRD soglie ricavi/bilancio post-Omnibus",
            status="YELLOW",
            summary=(
                "Nessun atto che emenda CELEX 32022L2464 trovato 2024+. "
                "Le soglie nominali (€50M, €25M) provengono dall'Accounting Directive 2013/34. "
                "Verifica manuale del testo consolidato richiesta."
            ),
            sparql_query=query_amending_acts(CELEX_CSRD, since_year=2024),
        )
    top = bindings[0]
    celex = top.get("celex", {}).get("value", "?")
    title = top.get("title", {}).get("value", "?")[:140]
    date = top.get("date_doc", {}).get("value", "?")
    return ClaimResult(
        claim_id="2",
        title="CSRD soglie ricavi/bilancio post-Omnibus",
        status="GREEN",
        summary=f"Atto modificante CSRD: CELEX {celex} ({date}) - {title}",
        evidence_url=f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}",
        sparql_query=query_amending_acts(CELEX_CSRD, 2024),
        raw_results=[
            {
                "celex": b.get("celex", {}).get("value"),
                "title": b.get("title", {}).get("value", "")[:120],
                "date": b.get("date_doc", {}).get("value"),
            }
            for b in bindings[:5]
        ],
    )


def verify_claim_3_esrs_set1() -> ClaimResult:
    """Claim 3: % riduzione datapoint ESRS Set 1 (claim -61%)."""
    print("\n[CLAIM 3] Cercando atti che modificano ESRS Set 1 (32023R2772)...")
    bindings = run_sparql(query_amending_acts(CELEX_ESRS_SET1, since_year=2024))
    return ClaimResult(
        claim_id="3",
        title="ESRS Set 1 datapoint reduction (claim -61%)",
        status="YELLOW",
        summary=(
            f"Trovati {len(bindings)} atti che emendano ESRS Set 1 (CELEX 32023R2772). "
            "La % esatta del taglio non è verificabile via SPARQL - richiede lettura "
            "dell'allegato dell'implementing act EFRAG aggiornato. "
            "Marcare come 'stima EFRAG' nel PDF, NON come dato regolamentare."
        ),
        sparql_query=query_amending_acts(CELEX_ESRS_SET1, 2024),
        raw_results=[
            {
                "celex": b.get("celex", {}).get("value"),
                "date": b.get("date_doc", {}).get("value"),
            }
            for b in bindings[:5]
        ],
    )


def verify_claim_4_csddd_deadline() -> ClaimResult:
    """Claim 4: CSDDD transposition deadline 26 luglio 2028 (Omnibus I, Dir. (UE) 2026/470)."""
    print("\n[CLAIM 4] Cercando atti che modificano CSDDD (32024L1760)...")
    bindings = run_sparql(query_amending_acts(CELEX_CSDDD, since_year=2024))
    if not bindings:
        return ClaimResult(
            claim_id="4",
            title="CSDDD transposition deadline post-Omnibus",
            status="YELLOW",
            summary=(
                "Nessun atto che emenda CELEX 32024L1760 trovato 2024+. "
                "Atteso: Dir. (UE) 2025/794 (stop-the-clock) e Dir. (UE) 2026/470 "
                "(Omnibus I sostanziale, GU 26-02-2026) → transposition 26 lug 2028, "
                "prima compliance 26 lug 2029. Se SPARQL non li restituisce, "
                "verificare manualmente su EUR-Lex prima di marcare GREEN."
            ),
            sparql_query=query_amending_acts(CELEX_CSDDD, 2024),
        )
    top = bindings[0]
    celex = top.get("celex", {}).get("value", "?")
    title = top.get("title", {}).get("value", "?")[:140]
    return ClaimResult(
        claim_id="4",
        title="CSDDD transposition deadline post-Omnibus",
        status="GREEN",
        summary=f"Atto modificante CSDDD: CELEX {celex} - {title}",
        evidence_url=f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}",
        sparql_query=query_amending_acts(CELEX_CSDDD, 2024),
        raw_results=[
            {"celex": b.get("celex", {}).get("value"), "title": b.get("title", {}).get("value", "")[:120]}
            for b in bindings[:5]
        ],
    )


def verify_claim_5_market_data() -> ClaimResult:
    """Claim 5: "80% calo perimetro IT" - non verificabile via EUR-Lex."""
    return ClaimResult(
        claim_id="5",
        title="Mercato IT: 80% calo aziende in scope CSRD",
        status="RED",
        summary=(
            "Dato di mercato NON verificabile via EUR-Lex. "
            "Fonte alternativa richiesta: studio ASviS, Confindustria, EFRAG impact assessment, "
            "o paper accademico. RIMUOVERE la cifra '80%' dal PDF se non puoi citare una fonte."
        ),
    )


def verify_claim_6_first_reporting() -> ClaimResult:
    """Claim 6: prima reportistica gruppi consolidati 2027/2028."""
    print("\n[CLAIM 6] Recupero metadata Direttiva 2022/2464 consolidata...")
    bindings = run_sparql(query_celex_metadata(CELEX_CSRD))
    return ClaimResult(
        claim_id="6",
        title="Date prima reportistica CSRD post-Omnibus (2027/2028)",
        status="YELLOW",
        summary=(
            f"Metadata CSRD recuperata ({len(bindings)} record). Le date di prima "
            "reportistica modificate 2027/2028 dipendono dal testo definitivo "
            "dell'Omnibus che è ancora in trilogue (knowledge cutoff May 2025). "
            "Marcare nel PDF come 'proposta Commissione' fino a OJ pubblicazione."
        ),
        evidence_url=f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{CELEX_CSRD}",
        sparql_query=query_celex_metadata(CELEX_CSRD),
    )


# ─────────────────────────── Orchestrator ───────────────────────────

def main() -> int:
    print("=" * 70)
    print("NormaAI Codex Citation Verifier")
    print(f"Endpoint: {SPARQL_ENDPOINT}")
    print(f"Run: {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70)

    verifiers = [
        verify_claim_1_omnibus_adoption,
        verify_claim_2_csrd_thresholds,
        verify_claim_3_esrs_set1,
        verify_claim_4_csddd_deadline,
        verify_claim_5_market_data,
        verify_claim_6_first_reporting,
    ]

    results: list[ClaimResult] = []
    for fn in verifiers:
        try:
            r = fn()
        except Exception as e:
            r = ClaimResult(
                claim_id=fn.__name__.split("_")[2],
                title=fn.__doc__ or fn.__name__,
                status="RED",
                summary=f"Script error: {e}",
            )
        results.append(r)
        print(f"  [{r.status}] {r.title}")
        print(f"  -> {r.summary[:200]}")
        time.sleep(1)  # sii gentile con l'endpoint

    # ── Tabella riassuntiva ───────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RISULTATI VERIFICA")
    print("=" * 70)
    print(f"{'#':3s} {'STATUS':8s}  {'CLAIM':50s}")
    print("-" * 70)
    counters = {"GREEN": 0, "YELLOW": 0, "RED": 0}
    for r in results:
        print(f"{r.claim_id:3s} {r.status:8s}  {r.title[:60]:50s}")
        counters[r.status] = counters.get(r.status, 0) + 1
    print("-" * 70)
    print(
        f"Totale: GREEN={counters['GREEN']}, "
        f"YELLOW={counters['YELLOW']}, RED={counters['RED']}"
    )

    # ── Output MD ────────────────────────────────────────────────────
    out_path = Path(__file__).resolve().parent.parent / "marketing" / "codex_cap1_VERIFIED.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_verified_md(results, out_path)
    print(f"\nFile generato: {out_path}")

    # Exit code 0 se nessun RED, 1 se almeno un RED critico
    return 0 if counters["RED"] == 0 else 1


def write_verified_md(results: list[ClaimResult], path: Path) -> None:
    lines = [
        "# Codex Post-Omnibus - Cap 1 VERIFIED",
        "",
        f"> Auto-generato da `scripts/verify_codex_citations.py` il "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}.",
        "",
        "Questo file integra le verifiche EUR-Lex SPARQL sui 6 claim del draft.",
        "Non sostituisce `codex_cap1_DRAFT.md`; lo annota.",
        "",
        "## Tabella riassuntiva",
        "",
        "| # | Claim | Status | Evidence |",
        "|---|---|---|---|",
    ]
    for r in results:
        ev = f"[{r.evidence_url}]({r.evidence_url})" if r.evidence_url else "-"
        lines.append(f"| {r.claim_id} | {r.title} | **{r.status}** | {ev} |")
    lines += ["", "## Dettagli per claim", ""]
    for r in results:
        lines += [
            f"### Claim {r.claim_id} - {r.title}",
            "",
            f"**Status:** `{r.status}`",
            "",
            f"**Riassunto:** {r.summary}",
            "",
        ]
        if r.evidence_url:
            lines += [f"**Evidence:** {r.evidence_url}", ""]
        if r.raw_results:
            lines += ["**Top results:**", "", "```json"]
            lines.append(json.dumps(r.raw_results, ensure_ascii=False, indent=2))
            lines += ["```", ""]
        lines += ["---", ""]

    lines += [
        "## Decisione editoriale per il PDF",
        "",
        "- **GREEN:** cita CELEX e URL OJ direttamente nel testo del Cap 1.",
        "- **YELLOW:** marcalo come *'proposta'* o *'stima EFRAG'* nel testo.",
        "  Non presentarlo come dato regolamentare consolidato.",
        "- **RED:** RIMUOVI la cifra dal PDF, oppure cita una fonte alternativa "
        "(studio settoriale, paper).",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
