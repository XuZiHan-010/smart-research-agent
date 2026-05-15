"""Resolve [cite:doc_id] markers after editor generation."""

from typing import Any, Dict

from backend.classes.state import ResearchState
from backend.services import mongodb_service as db
from backend.services.citation_service import collect_citations, resolve_citations


async def citation_resolver_node(state: ResearchState) -> Dict[str, Any]:
    citations = collect_citations(state.get("theme_reports", []))
    resolved, citation_map = resolve_citations(state.get("report", ""), citations)
    await db.update_job(state["job_id"], {"report": resolved, "citations_map": citation_map})
    return {
        "report": resolved,
        "final_report_md": resolved,
        "citations_map": citation_map,
        "events": [{"type": "status", "node": "citation_resolver", "message": "引用已解析为编号来源清单"}],
    }
