"""
LangGraph StateGraph — Competitor Research Agent pipeline.

Full pipeline:
  router
    → grounding
      → research_dispatcher          (N×M parallel; asyncio.gather inside)
        → collector                  (fan-in aggregator; builds todo_state)
          → curator                  (score/filter/enrich; writes MongoDB)
            → evaluator              (pure-rules quality gate)
              ├─[retry]──────────────→ research_dispatcher  (failed dims only)
              └─[pass]──→ comparator (6 dim narratives; Gemini 2.5 Flash)
                           → battlecard_builder  (JSON extraction; GPT-4.1-mini)
                             → editor            (prose report; GPT-4.1 streaming)
                               → output_formatter → END

Key design choices:
  - research_dispatcher handles N×M concurrency internally (dynamic fan-out)
  - evaluator conditional edge: retry_dimensions non-empty → loop back
  - all_company_names derived once at init; passed through state
  - edit jobs skip research by starting at editor directly (quick_edit)
    or run the full pipeline with edit_mode set (targeted/full refresh)
"""

import uuid
from typing import Dict, Any, List, AsyncIterator

from langgraph.graph import StateGraph, END

from backend.classes.state import CompetitorResearchState
from backend.nodes.router              import router_node
from backend.nodes.grounding           import grounding_node
from backend.nodes.research_dispatcher import research_dispatcher_node
from backend.nodes.collector           import collector_node
from backend.nodes.curator             import curator_node
from backend.nodes.evaluator           import evaluator_node
from backend.nodes.comparator          import comparator_node
from backend.nodes.battlecard_builder  import battlecard_builder_node
from backend.nodes.battlecard_validator import battlecard_validator_node
from backend.nodes.editor              import editor_node
from backend.nodes.output_formatter    import output_formatter_node


# ── Conditional routing ───────────────────────────────────────────────────────

def _route_after_evaluator(state: CompetitorResearchState) -> str:
    """
    If the quality gate failed and retry dimensions are set → loop back to
    research_dispatcher (which will run only the failed dimensions).
    Otherwise proceed to comparator.
    """
    if state.get("retry_dimensions") and not state.get("evaluation_passed", True):
        return "research_dispatcher"
    return "comparator"


def _route_after_validator(state: CompetitorResearchState) -> str:
    """
    If validator finds blocking quality issues and asks for targeted retry,
    loop back to research_dispatcher for failed dimensions.
    """
    report = state.get("validation_report", {}) or {}
    if report.get("should_retry") and report.get("retry_dimensions"):
        return "research_dispatcher"
    return "editor"


# ── Graph builder ─────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    wf = StateGraph(CompetitorResearchState)

    # Register all nodes
    wf.add_node("router",              router_node)
    wf.add_node("grounding",           grounding_node)
    wf.add_node("research_dispatcher", research_dispatcher_node)
    wf.add_node("collector",           collector_node)
    wf.add_node("curator",             curator_node)
    wf.add_node("evaluator",           evaluator_node)
    wf.add_node("comparator",          comparator_node)
    wf.add_node("battlecard_builder",  battlecard_builder_node)
    wf.add_node("battlecard_validator", battlecard_validator_node)
    wf.add_node("editor",              editor_node)
    wf.add_node("output_formatter",    output_formatter_node)

    # Linear edges
    wf.set_entry_point("router")
    wf.add_edge("router",             "grounding")
    wf.add_edge("grounding",          "research_dispatcher")
    wf.add_edge("research_dispatcher","collector")
    wf.add_edge("collector",          "curator")
    wf.add_edge("curator",            "evaluator")
    wf.add_edge("comparator",         "battlecard_builder")
    wf.add_edge("battlecard_builder", "battlecard_validator")
    wf.add_edge("editor",             "output_formatter")
    wf.add_edge("output_formatter",   END)

    # Conditional edge after evaluator: retry OR continue
    wf.add_conditional_edges(
        "evaluator",
        _route_after_evaluator,
        {
            "research_dispatcher": "research_dispatcher",
            "comparator":          "comparator",
        },
    )
    wf.add_conditional_edges(
        "battlecard_validator",
        _route_after_validator,
        {
            "research_dispatcher": "research_dispatcher",
            "editor":              "editor",
        },
    )

    return wf.compile()


_COMPILED_GRAPH = _build_graph()


# ── Public Graph class ────────────────────────────────────────────────────────

class Graph:
    """
    Wraps the compiled LangGraph pipeline.
    One instance per API request (holds initial_state and final_state).
    """

    def __init__(
        self,
        target_company:   str,
        target_website:   str,
        all_companies:    List[Dict[str, str]],  # [{name, website, source}]
        report_type:      str = "full_analysis",
        depth:            str = "standard",
        output_format:    str = "markdown",
        language:         str = "en",
        template:         str = "",
        job_id:           str | None = None,
        # edit-mode fields (optional — only set for edit jobs)
        edit_mode:        str = "",
        edit_instruction: str = "",
        report:           str = "",   # existing report for quick/targeted edit
        report_version:   int = 0,
    ) -> None:
        self._job_id = job_id or str(uuid.uuid4())
        self._final_state: Dict[str, Any] = {}

        # Derive flat name list once (used by grounding, dispatcher, collector…)
        all_company_names = [c["name"] for c in all_companies]

        self.initial_state: CompetitorResearchState = {
            # ── InputState fields ──────────────────────────────────────────
            "target_company":  target_company,
            "target_website":  target_website,
            "competitors":     [c["name"] for c in all_companies
                                if c.get("source") != "target"],
            "report_type":     report_type,
            "depth":           depth,
            "output_format":   output_format,
            "language":        language,
            "template":        template,
            "job_id":          self._job_id,

            # ── Discovery (pre-resolved before graph launch) ───────────────
            "confirmed_competitors": all_companies,
            "suggested_competitors": [],
            "needs_confirmation":    False,
            "all_companies":         all_companies,
            "all_company_names":     all_company_names,
            "competitor_rationale": {
                c["name"]: {
                    "why_included": c.get("reason", ""),
                    "threat_type": c.get("threat_type", "direct_competitor"),
                }
                for c in all_companies
                if c["name"] != target_company
            },
            "research_scope": {
                "lens": "multi_business_mix",
                "business_units": [],
                "comparison_basis": (
                    "Compare companies on selected dimensions and flag business-unit mismatch "
                    "when competitors are not directly comparable."
                ),
            },

            # ── Router output (filled by router_node) ──────────────────────
            "active_dimensions":   [],
            "queries_per_dim":     4,
            "results_per_query":   5,
            "max_docs_per_dim":    15,
            "comparator_focus":    "",
            "default_template":    "",

            # ── Grounding ──────────────────────────────────────────────────
            "site_scrapes": {},

            # ── Researchers fan-in ─────────────────────────────────────────
            "research_results": [],

            # ── Collector ─────────────────────────────────────────────────
            "todo_state":         {},
            "collection_summary": {},

            # ── Curator ───────────────────────────────────────────────────
            "curated_ref":    self._job_id,
            "references":     [],
            "curation_stats": {},

            # ── Evaluator ─────────────────────────────────────────────────
            "evaluation_passed":  False,
            "evaluation_report":  {},
            "retry_dimensions":   [],
            "retry_count":        0,

            # ── Comparator ────────────────────────────────────────────────
            "comparisons": {},
            "dimension_evidence": {},

            # ── Battlecard ────────────────────────────────────────────────
            "battlecard_data": {},

            # ── Editor (edit-mode) ─────────────────────────────────────────
            "edit_mode":        edit_mode,
            "edit_instruction": edit_instruction,
            "report_version":   report_version,

            # ── Final output ──────────────────────────────────────────────
            "report": report,
            "output": None,
            "quality_flags": [],
            "validation_report": {},

            # ── SSE event queue ────────────────────────────────────────────
            "events": [],
            "error":  "",
        }

    @property
    def job_id(self) -> str:
        return self._job_id

    # ── Streaming interface ───────────────────────────────────────────────────

    async def run(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Async generator — yields SSE event dicts as the pipeline progresses.
        Captures final state internally so get_final_state() works after completion.
        """
        async for chunk in _COMPILED_GRAPH.astream(
            self.initial_state,
            stream_mode="updates",
        ):
            for _node, delta in chunk.items():
                if not isinstance(delta, dict):
                    continue
                # Accumulate into final state (last writer wins for each key)
                self._final_state.update(
                    {k: v for k, v in delta.items() if k != "events"}
                )
                for event in delta.get("events", []):
                    yield event

    def get_final_state(self) -> Dict[str, Any]:
        """Return accumulated state after run() completes."""
        return self._final_state

    # ── Non-streaming interface (for tests) ───────────────────────────────────

    async def run_full(self) -> Dict[str, Any]:
        """Run to completion, return final state. Consumes all events."""
        async for _ in self.run():
            pass
        return self.get_final_state()
