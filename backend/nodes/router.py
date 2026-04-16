"""
Router node — translates user-facing inputs into concrete pipeline parameters.

Pure Python, no LLM call.  Reads report_type + depth from state and looks up
the matching config in REPORT_TYPE_CONFIGS / DEPTH_CONFIGS.

Outputs added to state:
  active_dimensions  — which of the 6 dimensions to research
  queries_per_dim    — Exa queries per dimension (from depth)
  results_per_query  — Exa results per query (from depth)
  max_docs_per_dim   — curator cap per dimension (from depth)
  comparator_focus   — hint string passed to comparator prompts
  default_template   — resolved system template text (or user template preserved)
"""

from typing import Dict, Any
from backend.classes.config import (
    REPORT_TYPE_CONFIGS,
    DEPTH_CONFIGS,
    VALID_REPORT_TYPES,
    VALID_DEPTHS,
    DIMENSION_LABELS_EN,
)
from backend.classes.state import CompetitorResearchState

# ── Default report templates (minimal — full versions written in Module 4) ─────

_DEFAULT_TEMPLATES: Dict[str, str] = {
    "full_analysis": """\
# {target_company} — Competitive Intelligence Report
**Date**: {date} | **Analysed against**: {competitors}

## Executive Summary

## 1. Product & Pricing Comparison

## 2. Market Positioning

## 3. Traction & Growth

## 4. Customer Sentiment

## 5. Content & Go-to-Market

## 6. Recent Activity & News

## 7. Strategic Implications

## 8. Battlecard Summary

## Sources
""",
    "pricing_focus": """\
# {target_company} — Pricing & Product Comparison
**Date**: {date} | **vs**: {competitors}

## Executive Summary

## Feature Comparison Matrix

## Pricing Tiers

## Differentiation & Positioning

## Verdict

## Sources
""",
    "investor_teardown": """\
# {target_company} — Investor Teardown
**Date**: {date} | **vs**: {competitors}

## Executive Summary

## Traction & Growth Metrics

## Market Opportunity & Positioning

## Competitive Moats

## Recent Signals

## Investment Thesis

## Sources
""",
    "customer_voice": """\
# {target_company} — Customer Voice Report
**Date**: {date} | **vs**: {competitors}

## Executive Summary

## Sentiment Overview

## What Customers Love

## Common Complaints & Churn Signals

## Recent Developments

## Implications

## Sources
""",
    "custom": "",   # replaced entirely by user-uploaded template
}


async def router_node(state: CompetitorResearchState) -> Dict[str, Any]:
    """
    Deterministic routing — no LLM, no I/O.
    Validates user inputs and resolves pipeline parameters.
    """
    report_type = state.get("report_type", "full_analysis")
    depth       = state.get("depth", "standard")
    template    = state.get("template", "").strip()

    # ── validate inputs, fall back to defaults if invalid ────────────────────
    if report_type not in VALID_REPORT_TYPES:
        report_type = "full_analysis"
    if depth not in VALID_DEPTHS:
        depth = "standard"

    rt_cfg    = REPORT_TYPE_CONFIGS[report_type]
    depth_cfg = DEPTH_CONFIGS[depth]

    active_dims      = rt_cfg["dimensions"]
    comparator_focus = rt_cfg["comparator_focus"]

    # User-provided template takes priority; otherwise use system default
    if template:
        resolved_template = template
    elif report_type == "custom":
        # custom without upload → fall back to full_analysis template
        resolved_template = _DEFAULT_TEMPLATES["full_analysis"]
    else:
        resolved_template = _DEFAULT_TEMPLATES[report_type]

    dim_labels = [DIMENSION_LABELS_EN[d] for d in active_dims]
    event = {
        "type":    "status",
        "node":    "router",
        "message": (
            f"Report type: {rt_cfg['label']} | "
            f"Depth: {depth_cfg['label']} (~{depth_cfg['estimated_minutes']} min) | "
            f"Dimensions: {', '.join(dim_labels)}"
        ),
    }

    return {
        "active_dimensions": active_dims,
        "queries_per_dim":   depth_cfg["queries_per_dim"],
        "results_per_query": depth_cfg["results_per_query"],
        "max_docs_per_dim":  depth_cfg["max_docs_per_dim"],
        "comparator_focus":  comparator_focus,
        "default_template":  resolved_template,
        "events":            [event],
    }
