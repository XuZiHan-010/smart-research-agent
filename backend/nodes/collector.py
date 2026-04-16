"""
Collector node — fan-in aggregator after all parallel researchers complete.

Reads:
  research_results  List[ResearchResultDict]  (accumulated via operator.add reducer)
  active_dimensions List[str]
  all_company_names List[str]

Writes:
  todo_state         {company: {dimension: {status, docs_found}}}
  collection_summary {total_docs, total_companies, total_dimensions, errors:[]}
  events             [todo event, status event]

The todo_state drives the N×M progress matrix in the frontend.
This node does NO filtering or enrichment — that is Curator's job.
"""

from typing import Dict, Any, List

from backend.classes.state import CompetitorResearchState
from backend.classes.config import DIMENSION_LABELS_EN


async def collector_node(state: CompetitorResearchState) -> Dict[str, Any]:
    results:    List[Dict] = state.get("research_results", [])
    companies:  List[str]  = state.get("all_company_names", [])
    dimensions: List[str]  = state.get("active_dimensions", [])

    # ── Build N×M todo_state matrix ──────────────────────────────────────────
    # Initialise every cell as "pending" so the frontend can show a full grid
    todo_state: Dict[str, Dict[str, Any]] = {
        company: {
            dim: {"status": "pending", "docs_found": 0}
            for dim in dimensions
        }
        for company in companies
    }

    errors:     List[str] = []
    total_docs: int       = 0

    for r in results:
        company   = r.get("company", "")
        dimension = r.get("dimension", "")
        status    = r.get("status", "error")
        docs_found = r.get("docs_found", 0)

        if company not in todo_state:
            todo_state[company] = {}

        todo_state[company][dimension] = {
            "status":    status,
            "docs_found": docs_found,
        }

        total_docs += docs_found

        if status == "error":
            errors.append(
                f"{company}/{dimension}: "
                f"{r.get('error_code','?')} — {r.get('error_message','')}"
            )

    # ── Summary ──────────────────────────────────────────────────────────────
    collection_summary = {
        "total_docs":       total_docs,
        "total_companies":  len(companies),
        "total_dimensions": len(dimensions),
        "errors":           errors,
    }

    dim_labels = {d: DIMENSION_LABELS_EN.get(d, d) for d in dimensions}

    events = [
        # todo event — frontend renders the progress matrix from this
        {
            "type":       "todo",
            "todo_state": todo_state,
            "dim_labels": dim_labels,
        },
        {
            "type":    "status",
            "node":    "collector",
            "message": (
                f"Collection complete — {total_docs} total docs | "
                f"{len(companies)} companies | "
                f"{len(errors)} errors"
            ),
        },
    ]

    return {
        "todo_state":         todo_state,
        "collection_summary": collection_summary,
        "events":             events,
    }
