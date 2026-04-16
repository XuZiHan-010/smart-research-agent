"""
Competitor Research Agent — State Definitions

Three things live here:
  1. Reducer helpers for LangGraph fan-in
  2. InputState  — the graph entry point (user-facing fields only)
  3. CompetitorResearchState — full pipeline state accumulated across all nodes
  4. job_status  — in-process FastAPI tracker (SSE event queue)
"""

import operator
from typing import TypedDict, List, Dict, Any, Annotated
from datetime import datetime
from collections import defaultdict


# ── Reducer helpers ───────────────────────────────────────────────────────────

def merge_dicts(a: Dict, b: Dict) -> Dict:
    """Shallow-merge two dicts; used as LangGraph reducer for fan-in nodes."""
    return {**a, **b}


# ── Input State ───────────────────────────────────────────────────────────────

class InputState(TypedDict):
    """
    User-supplied inputs — the graph entry point.
    Every field here maps directly to a frontend form control.
    """
    target_company:  str          # the company being analysed
    target_website:  str          # optional official URL; "" if not provided
    competitors:     List[str]    # user-typed competitor names (may be empty)
    report_type:     str          # "full_analysis"|"pricing_focus"|"investor_teardown"|"customer_voice"|"custom"
    depth:           str          # "snapshot"|"standard"|"deep_dive"
    output_format:   str          # "markdown"|"pdf"|"json"
    template:        str          # raw template text; "" means use system default
    language:        str          # "en" | "zh" — report output language
    job_id:          str          # UUID assigned by FastAPI before graph launch


# ── Full Pipeline State ───────────────────────────────────────────────────────

class CompetitorResearchState(TypedDict):
    """
    Accumulated state flowing through all LangGraph nodes.

    Section order matches the pipeline execution order:
      inputs → router → discovery → grounding → researchers (fan-in)
      → collector → curator → evaluator → comparator
      → battlecard → editor → formatter
    """

    # ── user inputs (copied from InputState) ─────────────────────────────────
    target_company:  str
    target_website:  str
    competitors:     List[str]
    report_type:     str
    depth:           str
    output_format:   str
    template:        str
    language:        str          # "en" | "zh"
    job_id:          str

    # ── router output ─────────────────────────────────────────────────────────
    # Determined by REPORT_TYPE_CONFIGS + DEPTH_CONFIGS — no LLM involved.
    active_dimensions:   List[str]     # subset of AVAILABLE_DIMENSIONS
    queries_per_dim:     int
    results_per_query:   int
    max_docs_per_dim:    int
    comparator_focus:    str           # hint for comparator prompts
    default_template:    str           # resolved system template text

    # ── discovery output ──────────────────────────────────────────────────────
    # confirmed_competitors = user-provided (always trusted)
    # suggested_competitors = auto-discovered (requires user confirmation)
    # all_companies is None until user confirms (or auto-skipped for ≥4 competitors)
    confirmed_competitors:  List[Dict[str, str]]
    # each: {name: str, source: "user"}

    suggested_competitors:  List[Dict[str, Any]]
    # each: {name: str, website: str, score: float, default_checked: bool}

    needs_confirmation:     bool
    # True = frontend must show DiscoveryPanel before pipeline continues

    all_companies:          List[Dict[str, str]]
    # confirmed after user interaction: [{name, website, source}]

    all_company_names:      List[str]
    # flat list derived from all_companies; used throughout pipeline
    competitor_rationale:   Dict[str, Dict[str, str]]
    # {company_name: {why_included: str, threat_type: str}}
    research_scope: Dict[str, Any]
    # {
    #   lens: str,             # single_business_unit | multi_business_mix
    #   business_units: [str], # inferred business clusters
    #   comparison_basis: str, # explicit comparison basis used in report
    # }

    # ── grounding output ──────────────────────────────────────────────────────
    site_scrapes:  Dict[str, str]
    # {company_name: crawled_homepage_text (max GROUNDING_MAX_CHARS chars)}

    # ── researchers output (fan-in via reducer) ───────────────────────────────
    # Each researcher appends one dict to this list.
    # Annotated[..., operator.add] tells LangGraph to concat lists across parallel nodes.
    research_results: Annotated[List[Dict[str, Any]], operator.add]
    # each dict schema:
    # {
    #   status:         "success"|"partial"|"empty"|"error"
    #   company:        str
    #   dimension:      str
    #   docs:           [{url, title, content, score, published_date}]
    #   queries_run:    int
    #   docs_found:     int
    #   unique_domains: int
    #   error_code:     "NO_RESULTS"|"API_TIMEOUT"|"RATE_LIMIT"|"EXCEPTION"|None
    #   error_message:  str|None
    # }

    # ── collector output ──────────────────────────────────────────────────────
    todo_state:  Dict[str, Dict[str, Any]]
    # {company: {dimension: {status: str, docs_found: int}}}
    # Drives the N×M progress matrix in the frontend.

    collection_summary: Dict[str, Any]
    # {total_docs: int, total_companies: int, total_dimensions: int, errors: [...]}

    # ── curator output ────────────────────────────────────────────────────────
    # curated_ref = job_id string → downstream nodes fetch curated data
    # from MongoDB on demand; full data is NOT stored in State.
    curated_ref:     str

    references:      List[str]
    # top-N deduplicated URLs across all companies/dimensions (for Sources section)

    curation_stats:  Dict[str, Any]
    # {
    #   total_docs_in:  int
    #   total_docs_out: int
    #   companies:      [str]
    #   dim_stats:      {dimension: {company: doc_count}}
    # }
    # Passed directly to evaluator; not exposed in final report.

    # ── evaluator output ──────────────────────────────────────────────────────
    evaluation_passed:  bool
    # True = proceed to comparator; False = retry or force-pass with partial data

    evaluation_report:  Dict[str, Any]
    # {dimension: {status: "pass"|"warn"|"fail", coverage: float, issues: [str]}}

    retry_dimensions:   List[str]
    # dimension keys to re-research (populated only when evaluation_passed=False)

    retry_count:     int
    # incremented each time evaluator routes back to research_dispatcher

    # ── comparator output ─────────────────────────────────────────────────────
    comparisons:  Dict[str, str]
    # {dimension: "cross-company comparison narrative text"}
    dimension_evidence: Dict[str, Dict[str, Any]]
    # {
    #   dimension: {
    #      narrative: str,
    #      confidence: "high"|"medium"|"low",
    #      data_gaps: [str],
    #      evidence: [{company,url,title,published_date,excerpt,confidence}],
    #      comparison_basis: str,
    #   }
    # }

    # ── battlecard output ─────────────────────────────────────────────────────
    battlecard_data:  Dict[str, Any]
    # {
    #   target:             str
    #   competitors:        [str]
    #   feature_matrix:     [{feature, companies: {name: "✅"|"⚠️"|"❌"}}]
    #   pricing_comparison: [{company, model, starting_price, enterprise_price}]
    #   win_themes:         [{vs_competitor, theme, evidence}]
    #   lose_themes:        [{vs_competitor, theme, evidence}]
    #   key_risks:          [str]
    #   generated_at:       ISO datetime str
    # }

    # ── editor inputs (only set for edit jobs) ───────────────────────────────
    edit_mode:        str    # "quick_edit" | "targeted_refresh" | "full_refresh" | ""
    edit_instruction: str    # free-text user instruction for edit
    report_version:   int    # incremented by editor on each successful edit

    # ── editor output ─────────────────────────────────────────────────────────
    report:  str    # final markdown report (streamed token-by-token to frontend)

    # ── formatter output ──────────────────────────────────────────────────────
    output:  Any    # str (markdown) | bytes (PDF) | dict (JSON battlecard export)
    quality_flags: List[Dict[str, Any]]
    # [{severity: "warn"|"fail", code: str, message: str, dimension?: str}]
    validation_report: Dict[str, Any]
    # {
    #   should_retry: bool,
    #   retry_dimensions: [str],
    #   checks: [{code, passed, detail}],
    #   summary: str,
    # }

    # ── shared / cross-cutting ────────────────────────────────────────────────
    events:  Annotated[List[Dict[str, Any]], operator.add]
    # SSE event queue — each node appends; FastAPI drains this to the browser.
    # Each event: {type: str, ...payload}
    # Known types: "status" | "todo" | "stream" | "complete" | "error"

    error:   str    # non-empty if any node raises an unrecoverable exception


# ── In-memory job tracker (FastAPI / SSE layer) ───────────────────────────────
# Keyed by job_id. Holds live state for the SSE streaming endpoint.
# Separate from LangGraph state — it's a simple dict, not a TypedDict.

job_status: Dict[str, Any] = defaultdict(lambda: {
    "status":        "pending",    # pending|processing|completed|failed
    "target_company": None,
    "report":         None,
    "output":         None,
    "output_format":  None,
    "error":          None,
    "events":         [],          # FIFO queue consumed by SSE endpoint
    "last_update":    datetime.now().isoformat(),
})
