"""
Output formatter node: convert final report into markdown/pdf/json.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List

from backend.classes.state import CompetitorResearchState
from backend.classes.config import DIMENSION_LABELS_EN, REPORT_TYPE_CONFIGS


async def output_formatter_node(state: CompetitorResearchState) -> Dict[str, Any]:
    fmt: str = state.get("output_format", "markdown").lower()
    report: str = state.get("report", "")
    target_company: str = state.get("target_company", "")
    all_companies: List[Dict[str, Any]] = state.get("all_companies", [])
    active_dims: List[str] = state.get("active_dimensions", [])
    comparisons: Dict[str, str] = state.get("comparisons", {})
    dimension_evidence: Dict[str, Dict[str, Any]] = state.get("dimension_evidence", {})
    competitor_rationale: Dict[str, Dict[str, str]] = state.get("competitor_rationale", {})
    research_scope: Dict[str, Any] = state.get("research_scope", {})
    battlecard_data: Dict[str, Any] = state.get("battlecard_data", {})
    references: List[str] = state.get("references", [])
    report_type: str = state.get("report_type", "full_analysis")
    depth: str = state.get("depth", "standard")
    quality_flags: List[Dict[str, Any]] = state.get("quality_flags", [])
    validation_report: Dict[str, Any] = state.get("validation_report", {})

    events: List[Dict[str, Any]] = [
        {"type": "status", "node": "output_formatter", "message": f"Formatting output as {fmt}"}
    ]

    if fmt == "pdf":
        output = _to_pdf(report, target_company)
    elif fmt == "json":
        output = _to_json(
            target_company=target_company,
            all_companies=all_companies,
            active_dims=active_dims,
            comparisons=comparisons,
            dimension_evidence=dimension_evidence,
            competitor_rationale=competitor_rationale,
            research_scope=research_scope,
            battlecard_data=battlecard_data,
            references=references,
            report=report,
            report_type=report_type,
            depth=depth,
            quality_flags=quality_flags,
            validation_report=validation_report,
        )
    else:
        output = report

    events.append(
        {
            "type": "status",
            "node": "output_formatter",
            "message": f"Output ready - format: {fmt}",
            "format": fmt,
        }
    )
    return {"output": output, "events": events}


def _to_pdf(markdown_text: str, company: str) -> bytes:
    from backend.services.pdf_service import PDFService

    service = PDFService()
    success, result = service.generate_pdf_bytes(markdown_text, company)
    if success:
        return result
    raise RuntimeError(f"PDF generation failed: {result}")


def _to_json(
    target_company: str,
    all_companies: List[Dict[str, Any]],
    active_dims: List[str],
    comparisons: Dict[str, str],
    dimension_evidence: Dict[str, Dict[str, Any]],
    competitor_rationale: Dict[str, Dict[str, str]],
    research_scope: Dict[str, Any],
    battlecard_data: Dict[str, Any],
    references: List[str],
    report: str,
    report_type: str,
    depth: str,
    quality_flags: List[Dict[str, Any]],
    validation_report: Dict[str, Any],
) -> Dict[str, Any]:
    rt_cfg = REPORT_TYPE_CONFIGS.get(report_type, REPORT_TYPE_CONFIGS["full_analysis"])
    competitor_names = [c["name"] for c in all_companies if c["name"] != target_company]

    comparison_sections: Dict[str, Any] = {}
    for dim in active_dims:
        narrative = comparisons.get(dim, "")
        label = DIMENSION_LABELS_EN.get(dim, dim)
        ev = dimension_evidence.get(dim, {})
        key_points = [
            line.lstrip("-* ").strip()
            for line in narrative.splitlines()
            if line.strip().startswith(("-", "*", "•")) and len(line.strip()) > 3
        ][:10]
        comparison_sections[dim] = {
            "label": label,
            "narrative": narrative,
            "key_points": key_points,
            "evidence_bundle": {
                "confidence": ev.get("confidence", "low"),
                "data_gaps": ev.get("data_gaps", []),
                "comparison_basis": ev.get("comparison_basis", ""),
                "evidence": ev.get("evidence", []),
            },
        }

    return {
        "metadata": {
            "target_company": target_company,
            "competitors": competitor_names,
            "report_type": report_type,
            "report_type_label": rt_cfg["label"],
            "depth": depth,
            "research_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "dimensions_researched": active_dims,
        },
        "research_scope": research_scope,
        "competitor_rationale": competitor_rationale,
        "comparisons": comparison_sections,
        "battlecard": battlecard_data,
        "quality_flags": quality_flags,
        "validation_report": validation_report,
        "references": references,
        "report_markdown": report,
    }

