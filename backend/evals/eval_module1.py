"""
Module 1 Evaluation — backend/classes/state.py + backend/classes/config.py

No API keys required. Pure structural and logical validation.
Tests are grouped into 5 categories:

  T1: Config internal consistency
  T2: State TypedDict structural checks
  T3: Reducer correctness
  T4: Config × State alignment
  T5: Edge-case and contract checks

Run:
  cd smart-research-agent
  python -m backend.evals.eval_module1
"""

import sys
import traceback
from typing import Any, Dict, List


# ── Test runner ───────────────────────────────────────────────────────────────

class EvalResult:
    def __init__(self):
        self.passed:  List[str] = []
        self.failed:  List[str] = []
        self.details: List[str] = []

    def ok(self, name: str, note: str = ""):
        self.passed.append(name)
        tag = f"  [note] {note}" if note else ""
        print(f"  PASS  {name}{tag}")

    def fail(self, name: str, reason: str):
        self.failed.append(name)
        self.details.append(f"{name}: {reason}")
        print(f"  FAIL  {name}")
        print(f"        {reason}")

    def section(self, title: str):
        print(f"\n{'─'*60}")
        print(f"  {title}")
        print(f"{'─'*60}")

    def summary(self):
        total = len(self.passed) + len(self.failed)
        print(f"\n{'='*60}")
        print(f"  Module 1 Evaluation Summary")
        print(f"{'='*60}")
        print(f"  Total : {total}")
        print(f"  Passed: {len(self.passed)}")
        print(f"  Failed: {len(self.failed)}")
        if self.failed:
            print(f"\n  Failed checks:")
            for d in self.details:
                print(f"    - {d}")
        score_pct = int(100 * len(self.passed) / total) if total else 0
        print(f"\n  Score : {score_pct}%")
        print(f"{'='*60}\n")
        return len(self.failed) == 0


r = EvalResult()

try:
    from backend.classes.config import (
        AVAILABLE_DIMENSIONS, DIMENSION_LABELS, DIMENSION_LABELS_EN,
        REPORT_TYPE_CONFIGS, DEPTH_CONFIGS,
        VALID_REPORT_TYPES, VALID_DEPTHS, VALID_OUTPUT_FORMATS,
        MAX_COMPETITORS, MIN_COMPETITORS, MAX_DISCOVERY_SUGGESTIONS,
        GROUNDING_MAX_CHARS, GROUNDING_QUERY_CHARS, DOC_MAX_CHARS,
        COMPARATOR_CONTEXT_MAX_CHARS, REFERENCES_MAX,
        EXA_BATCH_SIZE, EXA_SCORE_THRESHOLD,
        QUALITY_THRESHOLDS, AUTHORITATIVE_DOMAINS,
        SEMAPHORE_GROUNDING, SEMAPHORE_RESEARCHERS,
        SEMAPHORE_EXA_SEARCH, SEMAPHORE_COMPARATOR,
        MAX_RESEARCHER_RETRIES, RETRY_DELAY_BASE, MAX_EVALUATOR_RETRIES,
        STALE_DATA_DAYS,
    )
    from backend.classes.state import (
        InputState, CompetitorResearchState, job_status, merge_dicts,
    )
    r.ok("imports", "all config + state symbols imported cleanly")
except Exception as e:
    print(f"\nFATAL: import failed — {e}")
    traceback.print_exc()
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# T1: Config internal consistency
# ─────────────────────────────────────────────────────────────────────────────
r.section("T1: Config internal consistency")

# T1-1: AVAILABLE_DIMENSIONS has exactly 6 entries and no duplicates
if len(AVAILABLE_DIMENSIONS) == 6 and len(set(AVAILABLE_DIMENSIONS)) == 6:
    r.ok("T1-1 AVAILABLE_DIMENSIONS count=6, no duplicates")
else:
    r.fail("T1-1 AVAILABLE_DIMENSIONS", f"expected 6 unique, got {AVAILABLE_DIMENSIONS}")

# T1-2: DIMENSION_LABELS covers every dimension (no missing labels)
missing_zh = [d for d in AVAILABLE_DIMENSIONS if d not in DIMENSION_LABELS]
missing_en = [d for d in AVAILABLE_DIMENSIONS if d not in DIMENSION_LABELS_EN]
if not missing_zh and not missing_en:
    r.ok("T1-2 DIMENSION_LABELS complete (ZH + EN)")
else:
    r.fail("T1-2 DIMENSION_LABELS", f"missing ZH={missing_zh}, EN={missing_en}")

# T1-3: Every REPORT_TYPE_CONFIGS dimension is a subset of AVAILABLE_DIMENSIONS
bad_rt = {}
for rt, cfg in REPORT_TYPE_CONFIGS.items():
    unknown = [d for d in cfg["dimensions"] if d not in AVAILABLE_DIMENSIONS]
    if unknown:
        bad_rt[rt] = unknown
if not bad_rt:
    r.ok("T1-3 REPORT_TYPE_CONFIGS dimensions are subsets of AVAILABLE_DIMENSIONS")
else:
    r.fail("T1-3 REPORT_TYPE_CONFIGS", f"unknown dimensions: {bad_rt}")

# T1-4: Required keys present in every REPORT_TYPE_CONFIGS entry
required_rt_keys = {"label", "description", "dimensions", "comparator_focus", "template_key"}
bad_keys = {}
for rt, cfg in REPORT_TYPE_CONFIGS.items():
    missing = required_rt_keys - set(cfg.keys())
    if missing:
        bad_keys[rt] = missing
if not bad_keys:
    r.ok("T1-4 REPORT_TYPE_CONFIGS entries have all required keys")
else:
    r.fail("T1-4 REPORT_TYPE_CONFIGS keys", str(bad_keys))

# T1-5: VALID_REPORT_TYPES matches REPORT_TYPE_CONFIGS keys exactly
if set(VALID_REPORT_TYPES) == set(REPORT_TYPE_CONFIGS.keys()):
    r.ok("T1-5 VALID_REPORT_TYPES == REPORT_TYPE_CONFIGS keys")
else:
    r.fail("T1-5 VALID_REPORT_TYPES", f"{VALID_REPORT_TYPES} vs {list(REPORT_TYPE_CONFIGS)}")

# T1-6: 'custom' report type always uses ALL dimensions
custom_dims = set(REPORT_TYPE_CONFIGS["custom"]["dimensions"])
all_dims    = set(AVAILABLE_DIMENSIONS)
if custom_dims == all_dims:
    r.ok("T1-6 custom report type uses all dimensions")
else:
    r.fail("T1-6 custom dims", f"expected all 6, got {custom_dims}")

# T1-7: DEPTH_CONFIGS ordering: snapshot < standard < deep_dive
depths = DEPTH_CONFIGS
ok_order = (
    depths["snapshot"]["queries_per_dim"]  < depths["standard"]["queries_per_dim"]  < depths["deep_dive"]["queries_per_dim"] and
    depths["snapshot"]["results_per_query"] < depths["standard"]["results_per_query"] < depths["deep_dive"]["results_per_query"] and
    depths["snapshot"]["max_docs_per_dim"] < depths["standard"]["max_docs_per_dim"]  < depths["deep_dive"]["max_docs_per_dim"]
)
if ok_order:
    r.ok("T1-7 DEPTH_CONFIGS ordering: snapshot < standard < deep_dive")
else:
    r.fail("T1-7 DEPTH_CONFIGS ordering", "values not strictly increasing")

# T1-8: VALID_DEPTHS matches DEPTH_CONFIGS keys
if set(VALID_DEPTHS) == set(DEPTH_CONFIGS.keys()):
    r.ok("T1-8 VALID_DEPTHS == DEPTH_CONFIGS keys")
else:
    r.fail("T1-8 VALID_DEPTHS", f"{VALID_DEPTHS} vs {list(DEPTH_CONFIGS)}")

# T1-9: Estimated minutes are positive and in order
mins = [DEPTH_CONFIGS[d]["estimated_minutes"] for d in ["snapshot", "standard", "deep_dive"]]
if all(m > 0 for m in mins) and mins == sorted(mins):
    r.ok(f"T1-9 estimated_minutes positive and ordered: {mins}")
else:
    r.fail("T1-9 estimated_minutes", f"got {mins}")

# T1-10: Numeric constants are sane
checks = [
    ("MAX_COMPETITORS", MAX_COMPETITORS, 1, 20),
    ("MIN_COMPETITORS", MIN_COMPETITORS, 1, MAX_COMPETITORS),
    ("GROUNDING_MAX_CHARS", GROUNDING_MAX_CHARS, 1000, 50000),
    ("GROUNDING_QUERY_CHARS", GROUNDING_QUERY_CHARS, 100, GROUNDING_MAX_CHARS),
    ("DOC_MAX_CHARS", DOC_MAX_CHARS, 500, 10000),
    ("EXA_SCORE_THRESHOLD", EXA_SCORE_THRESHOLD, 0.0, 1.0),
    ("REFERENCES_MAX", REFERENCES_MAX, 1, 100),
    ("MAX_RESEARCHER_RETRIES", MAX_RESEARCHER_RETRIES, 0, 10),
    ("STALE_DATA_DAYS", STALE_DATA_DAYS, 1, 730),
]
bounds_ok = True
for name, val, lo, hi in checks:
    if not (lo <= val <= hi):
        r.fail(f"T1-10 {name}", f"expected [{lo}, {hi}], got {val}")
        bounds_ok = False
if bounds_ok:
    r.ok("T1-10 all numeric constants within sane bounds")

# T1-11: GROUNDING_QUERY_CHARS <= GROUNDING_MAX_CHARS
if GROUNDING_QUERY_CHARS <= GROUNDING_MAX_CHARS:
    r.ok("T1-11 GROUNDING_QUERY_CHARS <= GROUNDING_MAX_CHARS")
else:
    r.fail("T1-11", f"{GROUNDING_QUERY_CHARS} > {GROUNDING_MAX_CHARS}")

# T1-12: AUTHORITATIVE_DOMAINS covers every dimension
missing_ad = [d for d in AVAILABLE_DIMENSIONS if d not in AUTHORITATIVE_DOMAINS]
if not missing_ad:
    r.ok("T1-12 AUTHORITATIVE_DOMAINS covers all 6 dimensions")
else:
    r.fail("T1-12 AUTHORITATIVE_DOMAINS", f"missing: {missing_ad}")

# T1-13: Semaphore values are positive integers
sems = {"SEMAPHORE_GROUNDING": SEMAPHORE_GROUNDING, "SEMAPHORE_RESEARCHERS": SEMAPHORE_RESEARCHERS,
        "SEMAPHORE_EXA_SEARCH": SEMAPHORE_EXA_SEARCH, "SEMAPHORE_COMPARATOR": SEMAPHORE_COMPARATOR}
bad_sems = {k: v for k, v in sems.items() if not (isinstance(v, int) and v > 0)}
if not bad_sems:
    r.ok("T1-13 all semaphore values are positive integers")
else:
    r.fail("T1-13 semaphores", str(bad_sems))

# T1-14: QUALITY_THRESHOLDS has all required keys
required_qt = {"min_docs_per_dimension", "min_companies_coverage", "min_avg_score"}
missing_qt  = required_qt - set(QUALITY_THRESHOLDS.keys())
if not missing_qt:
    r.ok("T1-14 QUALITY_THRESHOLDS has all required keys")
else:
    r.fail("T1-14 QUALITY_THRESHOLDS", f"missing: {missing_qt}")

# T1-15: QUALITY_THRESHOLDS values in valid ranges
qt = QUALITY_THRESHOLDS
qt_ok = (
    isinstance(qt["min_docs_per_dimension"], int)  and qt["min_docs_per_dimension"] >= 1 and
    0 < qt["min_companies_coverage"] <= 1.0 and
    0 < qt["min_avg_score"]          <= 1.0
)
if qt_ok:
    r.ok("T1-15 QUALITY_THRESHOLDS values in valid ranges")
else:
    r.fail("T1-15 QUALITY_THRESHOLDS values", str(qt))


# ─────────────────────────────────────────────────────────────────────────────
# T2: State TypedDict structural checks
# ─────────────────────────────────────────────────────────────────────────────
r.section("T2: State TypedDict structural checks")

import typing

def get_hints(cls) -> set:
    try:
        return set(typing.get_type_hints(cls).keys())
    except Exception:
        return set(cls.__annotations__.keys())

input_fields = get_hints(InputState)
state_fields = get_hints(CompetitorResearchState)

# T2-1: InputState has all 8 required fields
expected_input = {"target_company","target_website","competitors","report_type",
                   "depth","output_format","template","language","job_id"}
if expected_input <= input_fields:
    r.ok("T2-1 InputState has all required user-input fields")
else:
    r.fail("T2-1 InputState fields", f"missing: {expected_input - input_fields}")

# T2-2: CompetitorResearchState is a superset of InputState fields
if input_fields <= state_fields:
    r.ok("T2-2 CompetitorResearchState is superset of InputState")
else:
    r.fail("T2-2 state superset", f"missing from State: {input_fields - state_fields}")

# T2-3: Pipeline output fields present
pipeline_fields = {
    "active_dimensions","queries_per_dim","results_per_query","max_docs_per_dim",
    "comparator_focus","default_template",
    "confirmed_competitors","suggested_competitors","needs_confirmation",
    "all_companies","all_company_names","competitor_rationale","research_scope",
    "site_scrapes","research_results","todo_state","collection_summary",
    "curated_ref","references","curation_stats",
    "evaluation_passed","evaluation_report","retry_dimensions","retry_count",
    "comparisons","dimension_evidence","battlecard_data","quality_flags","validation_report","report","output",
    "events","error",
}
missing_pipe = pipeline_fields - state_fields
if not missing_pipe:
    r.ok("T2-3 pipeline output fields present in CompetitorResearchState")
else:
    r.fail("T2-3 pipeline fields", f"missing: {missing_pipe}")

# T2-4: research_results uses Annotated (LangGraph fan-in reducer)
annotations = CompetitorResearchState.__annotations__
rr_annotation = str(annotations.get("research_results", ""))
if "Annotated" in rr_annotation or "operator.add" in rr_annotation:
    r.ok("T2-4 research_results uses Annotated reducer (fan-in safe)")
else:
    r.fail("T2-4 research_results annotation", f"got: {rr_annotation}")

# T2-5: events uses Annotated (fan-in reducer)
ev_annotation = str(annotations.get("events", ""))
if "Annotated" in ev_annotation or "operator.add" in ev_annotation:
    r.ok("T2-5 events uses Annotated reducer (fan-in safe)")
else:
    r.fail("T2-5 events annotation", f"got: {ev_annotation}")

# T2-6: curated_ref is str (not a full data dump)
from typing import get_type_hints
try:
    hints = get_type_hints(CompetitorResearchState)
    cr_type = hints.get("curated_ref")
    if cr_type is str:
        r.ok("T2-6 curated_ref is str (pointer, not full data — State stays slim)")
    else:
        r.fail("T2-6 curated_ref type", f"expected str, got {cr_type}")
except Exception as e:
    r.fail("T2-6 curated_ref type", f"type hint check failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# T3: Reducer correctness
# ─────────────────────────────────────────────────────────────────────────────
r.section("T3: Reducer correctness")

# T3-1: merge_dicts basic
assert merge_dicts({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
r.ok("T3-1 merge_dicts: disjoint keys")

# T3-2: merge_dicts — b overwrites a on conflict (shallow merge)
result = merge_dicts({"x": 1}, {"x": 99})
if result == {"x": 99}:
    r.ok("T3-2 merge_dicts: b overwrites a on key conflict")
else:
    r.fail("T3-2 merge_dicts conflict", f"got {result}")

# T3-3: merge_dicts — empty inputs
if merge_dicts({}, {}) == {}:
    r.ok("T3-3 merge_dicts: both empty")
else:
    r.fail("T3-3 merge_dicts empty", "should return {}")

# T3-4: merge_dicts — does not mutate inputs
a = {"k": 1}
b = {"k": 2}
_ = merge_dicts(a, b)
if a == {"k": 1} and b == {"k": 2}:
    r.ok("T3-4 merge_dicts: does not mutate inputs")
else:
    r.fail("T3-4 merge_dicts mutation", "inputs were mutated")

# T3-5: operator.add simulation for research_results fan-in
import operator
list_a = [{"company": "A", "dimension": "product_pricing"}]
list_b = [{"company": "B", "dimension": "market_position"}]
merged = operator.add(list_a, list_b)
if len(merged) == 2 and merged[0]["company"] == "A" and merged[1]["company"] == "B":
    r.ok("T3-5 operator.add merges research_results lists correctly")
else:
    r.fail("T3-5 operator.add", f"got {merged}")


# ─────────────────────────────────────────────────────────────────────────────
# T4: Config × State alignment
# ─────────────────────────────────────────────────────────────────────────────
r.section("T4: Config × State alignment")

# T4-1: InputState.report_type field aligns with VALID_REPORT_TYPES
# (runtime check: simulated router input → config lookup)
for rt in VALID_REPORT_TYPES:
    cfg = REPORT_TYPE_CONFIGS.get(rt)
    if cfg is None:
        r.fail(f"T4-1 lookup {rt}", "not found in REPORT_TYPE_CONFIGS")
        break
else:
    r.ok(f"T4-1 all VALID_REPORT_TYPES resolve in REPORT_TYPE_CONFIGS: {VALID_REPORT_TYPES}")

# T4-2: InputState.depth field aligns with VALID_DEPTHS
for d in VALID_DEPTHS:
    if d not in DEPTH_CONFIGS:
        r.fail(f"T4-2 lookup depth {d}", "not found in DEPTH_CONFIGS")
        break
else:
    r.ok(f"T4-2 all VALID_DEPTHS resolve in DEPTH_CONFIGS: {VALID_DEPTHS}")

# T4-3: InputState.output_format aligns with VALID_OUTPUT_FORMATS
if set(VALID_OUTPUT_FORMATS) == {"markdown", "pdf", "json"}:
    r.ok("T4-3 VALID_OUTPUT_FORMATS = {markdown, pdf, json}")
else:
    r.fail("T4-3 VALID_OUTPUT_FORMATS", str(VALID_OUTPUT_FORMATS))

# T4-4: State.active_dimensions will always be a subset of AVAILABLE_DIMENSIONS
# Verify by checking every report type's dimension list
all_subsets_ok = all(
    set(cfg["dimensions"]) <= set(AVAILABLE_DIMENSIONS)
    for cfg in REPORT_TYPE_CONFIGS.values()
)
if all_subsets_ok:
    r.ok("T4-4 all report type dimension lists are subsets of AVAILABLE_DIMENSIONS")
else:
    r.fail("T4-4 dimension subsets", "some report type uses unknown dimensions")

# T4-5: job_status default matches expected shape
js = job_status["__test_key__"]
required_js = {"status", "target_company", "report", "output", "output_format", "error", "events", "last_update"}
missing_js  = required_js - set(js.keys())
if not missing_js:
    r.ok("T4-5 job_status default has all required keys")
else:
    r.fail("T4-5 job_status shape", f"missing: {missing_js}")

# T4-6: job_status["events"] is a list (SSE queue)
if isinstance(js["events"], list):
    r.ok("T4-6 job_status events field is a list")
else:
    r.fail("T4-6 job_status events", f"got {type(js['events'])}")

# T4-7: job_status["status"] default is "pending"
if js["status"] == "pending":
    r.ok("T4-7 job_status default status is 'pending'")
else:
    r.fail("T4-7 job_status status", f"got '{js['status']}'")


# ─────────────────────────────────────────────────────────────────────────────
# T5: Edge-case and contract checks
# ─────────────────────────────────────────────────────────────────────────────
r.section("T5: Edge-case and contract checks")

# T5-1: MIN_COMPETITORS < MAX_COMPETITORS
if MIN_COMPETITORS < MAX_COMPETITORS:
    r.ok(f"T5-1 MIN_COMPETITORS ({MIN_COMPETITORS}) < MAX_COMPETITORS ({MAX_COMPETITORS})")
else:
    r.fail("T5-1 competitor bounds", f"MIN={MIN_COMPETITORS} MAX={MAX_COMPETITORS}")

# T5-2: max_docs_per_dim >= results_per_query for all depths
# (otherwise curator cap is hit before Exa even returns max results)
cap_ok = all(
    cfg["max_docs_per_dim"] >= cfg["results_per_query"]
    for cfg in DEPTH_CONFIGS.values()
)
if cap_ok:
    r.ok("T5-2 max_docs_per_dim >= results_per_query for all depths")
else:
    r.fail("T5-2 docs cap", "some depth has max_docs_per_dim < results_per_query")

# T5-3: COMPARATOR_CONTEXT_MAX_CHARS > DOC_MAX_CHARS * 3
# (comparator must fit at least a few docs in context)
if COMPARATOR_CONTEXT_MAX_CHARS > DOC_MAX_CHARS * 3:
    r.ok(f"T5-3 COMPARATOR_CONTEXT_MAX_CHARS ({COMPARATOR_CONTEXT_MAX_CHARS:,}) > DOC_MAX_CHARS*3")
else:
    r.fail("T5-3 context capacity", f"{COMPARATOR_CONTEXT_MAX_CHARS} not > {DOC_MAX_CHARS * 3}")

# T5-4: EXA_SCORE_THRESHOLD consistent with QUALITY_THRESHOLDS min_avg_score
# (threshold for keeping a doc should be <= the minimum acceptable average)
if EXA_SCORE_THRESHOLD <= QUALITY_THRESHOLDS["min_avg_score"]:
    r.ok(f"T5-4 EXA_SCORE_THRESHOLD ({EXA_SCORE_THRESHOLD}) <= min_avg_score ({QUALITY_THRESHOLDS['min_avg_score']})")
else:
    r.fail("T5-4 score threshold coherence",
           f"filter threshold {EXA_SCORE_THRESHOLD} > quality threshold {QUALITY_THRESHOLDS['min_avg_score']}")

# T5-5: MAX_EVALUATOR_RETRIES is bounded (prevent infinite loop)
if 0 <= MAX_EVALUATOR_RETRIES <= 3:
    r.ok(f"T5-5 MAX_EVALUATOR_RETRIES = {MAX_EVALUATOR_RETRIES} (bounded, no infinite loops)")
else:
    r.fail("T5-5 MAX_EVALUATOR_RETRIES", f"got {MAX_EVALUATOR_RETRIES}, expected 0–3")

# T5-6: RETRY_DELAY_BASE > 0
if RETRY_DELAY_BASE > 0:
    r.ok(f"T5-6 RETRY_DELAY_BASE = {RETRY_DELAY_BASE}s (positive)")
else:
    r.fail("T5-6 RETRY_DELAY_BASE", f"got {RETRY_DELAY_BASE}")

# T5-7: STALE_DATA_DAYS reasonable for competitive intel (30–365 days)
if 30 <= STALE_DATA_DAYS <= 365:
    r.ok(f"T5-7 STALE_DATA_DAYS = {STALE_DATA_DAYS} (30–365 range)")
else:
    r.fail("T5-7 STALE_DATA_DAYS", f"got {STALE_DATA_DAYS}, expected 30–365")

# T5-8: merge_dicts is idempotent when called with same dict twice
d = {"a": 1, "b": 2}
result = merge_dicts(d, d)
if result == d:
    r.ok("T5-8 merge_dicts(d, d) == d (idempotent)")
else:
    r.fail("T5-8 merge_dicts idempotent", f"got {result}")

# T5-9: DIMENSION_LABELS_EN values are non-empty strings
bad_labels = [k for k, v in DIMENSION_LABELS_EN.items() if not isinstance(v, str) or not v.strip()]
if not bad_labels:
    r.ok("T5-9 all DIMENSION_LABELS_EN values are non-empty strings")
else:
    r.fail("T5-9 DIMENSION_LABELS_EN values", f"bad keys: {bad_labels}")

# T5-10: No dimension appears in AVAILABLE_DIMENSIONS more than once
from collections import Counter
counts = Counter(AVAILABLE_DIMENSIONS)
dupes  = [k for k, v in counts.items() if v > 1]
if not dupes:
    r.ok("T5-10 AVAILABLE_DIMENSIONS has no duplicate entries")
else:
    r.fail("T5-10 duplicates", str(dupes))


# ─────────────────────────────────────────────────────────────────────────────
# Print summary
# ─────────────────────────────────────────────────────────────────────────────
passed = r.summary()
sys.exit(0 if passed else 1)
