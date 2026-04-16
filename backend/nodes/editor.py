"""
Editor node: compile comparison outputs into a final report (or edit existing report).
"""

import os
from datetime import datetime, timezone
from typing import Dict, Any, List

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from backend.classes.state import CompetitorResearchState
from backend.classes.config import DIMENSION_LABELS_EN, REPORT_TYPE_CONFIGS
from backend.prompts import EDITOR_COMPILE_PROMPT, EDITOR_EDIT_PROMPT
from backend.services import mongodb_service

load_dotenv()

_COMPARISONS_MAX_CHARS = 60_000
_BATTLECARD_MAX_CHARS = 5_000

# Must match the sentinel set in comparator.py
_FAILED_PREFIX = "@@COMPARISON_FAILED@@"

_ENCODING_FIXES = {
    "â¬": "€",
    "Â®": "®",
    "â": "'",
    "â": '"',
    "â": '"',
    "â": "-",
    "â": "-",
    "Â°": "°",
    "Â·": "·",
    "Â ": " ",
}


def _get_llm(streaming: bool = True) -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4.1",
        temperature=0.3,
        streaming=streaming,
        api_key=os.getenv("OPENAI_API_KEY", ""),
    )


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text
    for bad, good in _ENCODING_FIXES.items():
        cleaned = cleaned.replace(bad, good)
    return cleaned


def _format_comparisons(
    comparisons: Dict[str, str],
    active_dimensions: List[str],
    max_chars: int = _COMPARISONS_MAX_CHARS,
) -> tuple[str, List[str]]:
    """Return (formatted_text, list_of_failed_dimension_labels).

    Narratives prefixed with _FAILED_PREFIX are excluded from the main
    comparison text and their labels are collected so the editor prompt
    can mention them in a "data limitations" note instead.
    """
    successful = [d for d in active_dimensions if not _is_failed(comparisons.get(d, ""))]
    per_dim_budget = max_chars // max(len(successful), 1)

    parts: List[str] = []
    failed_labels: List[str] = []
    for dim in active_dimensions:
        narrative = _normalize_text(comparisons.get(dim, ""))
        if not narrative:
            continue
        if _is_failed(narrative):
            failed_labels.append(DIMENSION_LABELS_EN.get(dim, dim))
            continue
        label = DIMENSION_LABELS_EN.get(dim, dim)
        parts.append(f"## {label}\n\n{narrative[:per_dim_budget]}")

    text = "\n\n---\n\n".join(parts) or "No research comparisons available."
    return text, failed_labels


def _is_failed(narrative: str) -> bool:
    """Check if a comparator narrative is a failure placeholder."""
    return narrative.startswith(_FAILED_PREFIX)


def _format_battlecard_summary(battlecard: Dict[str, Any]) -> str:
    if not battlecard or battlecard.get("parse_error"):
        return "No battlecard data available."

    lines: List[str] = []
    features = battlecard.get("feature_matrix", [])
    if isinstance(features, list) and features:
        lines.append("Feature highlights:")
        for feat in features[:6]:
            name = _normalize_text(str(feat.get("feature", "")))
            cols = feat.get("companies", {}) if isinstance(feat, dict) else {}
            col_str = ", ".join(f"{k}: {v}" for k, v in cols.items()) if isinstance(cols, dict) else ""
            if name:
                lines.append(f"- {name}: {col_str}")

    wins = battlecard.get("win_themes", [])
    if isinstance(wins, list) and wins:
        lines.append("Win themes:")
        for row in wins[:4]:
            lines.append(
                f"- vs {row.get('vs_competitor', 'unknown')}: {_normalize_text(str(row.get('theme', '')))}"
            )

    loses = battlecard.get("lose_themes", [])
    if isinstance(loses, list) and loses:
        lines.append("Lose themes:")
        for row in loses[:4]:
            lines.append(
                f"- vs {row.get('vs_competitor', 'unknown')}: {_normalize_text(str(row.get('theme', '')))}"
            )

    gaps = battlecard.get("data_gaps", [])
    if isinstance(gaps, list) and gaps:
        lines.append("Data gaps:")
        lines.extend(f"- {_normalize_text(str(g))}" for g in gaps[:5])

    summary = "\n".join(lines)
    return _normalize_text(summary[:_BATTLECARD_MAX_CHARS])


def _format_references(references: List[str]) -> str:
    if not references:
        return "No references collected."
    return "\n".join(f"{i + 1}. {r}" for i, r in enumerate(references))


def _format_competitor_profiles(competitor_rationale: Dict[str, Dict[str, str]]) -> str:
    if not competitor_rationale:
        return "No explicit competitor rationale available."
    lines: List[str] = []
    for name, payload in competitor_rationale.items():
        why = _normalize_text(payload.get("why_included", "") or payload.get("reason", ""))
        threat_type = payload.get("threat_type", "direct_competitor")
        lines.append(f"- {name}: why included: {why or 'not provided'}; threat type: {threat_type}")
    return "\n".join(lines)


def _format_data_gap_confidence(dimension_evidence: Dict[str, Dict[str, Any]]) -> tuple[str, str]:
    if not dimension_evidence:
        return ("No explicit data gap annotations.", "None.")

    gap_lines: List[str] = []
    low_conf_lines: List[str] = []

    for dim, payload in dimension_evidence.items():
        label = DIMENSION_LABELS_EN.get(dim, dim)
        confidence = str(payload.get("confidence", "low")).lower()
        gaps = payload.get("data_gaps", []) or []

        if gaps:
            for gap in gaps:
                gap_lines.append(f"- {label}: {_normalize_text(str(gap))}")
        if confidence == "low":
            low_conf_lines.append(f"- {label}: low confidence.")
        elif confidence == "medium":
            low_conf_lines.append(f"- {label}: medium confidence; verify before hard claims.")

    return (
        "\n".join(gap_lines) if gap_lines else "No major data gaps detected.",
        "\n".join(low_conf_lines) if low_conf_lines else "None.",
    )


def _format_quality_flags(quality_flags: List[Dict[str, Any]], validation_report: Dict[str, Any]) -> str:
    lines: List[str] = []
    for flag in quality_flags or []:
        sev = str(flag.get("severity", "warn")).upper()
        code = flag.get("code", "UNKNOWN")
        msg = _normalize_text(str(flag.get("message", "")))
        dim = flag.get("dimension")
        if dim:
            lines.append(f"- [{sev}] {code} ({dim}): {msg}")
        else:
            lines.append(f"- [{sev}] {code}: {msg}")

    summary = _normalize_text(str((validation_report or {}).get("summary", "")))
    if summary:
        lines.append(f"- Validator summary: {summary}")
    return "\n".join(lines) if lines else "No critical quality flags."


def _market_lens_text(research_scope: Dict[str, Any]) -> tuple[str, str]:
    lens = research_scope.get("lens", "multi_business_mix")
    business_units = research_scope.get("business_units", []) or []
    basis = research_scope.get(
        "comparison_basis",
        "Compare competitors on selected dimensions and flag weak evidence explicitly.",
    )
    if business_units:
        return f"{lens} (business units: {', '.join(map(str, business_units[:5]))})", str(basis)
    return str(lens), str(basis)


async def editor_node(state: CompetitorResearchState) -> Dict[str, Any]:
    comparisons: Dict[str, str] = state.get("comparisons", {})
    dimension_evidence: Dict[str, Dict[str, Any]] = state.get("dimension_evidence", {})
    battlecard_data: Dict[str, Any] = state.get("battlecard_data", {})
    active_dimensions: List[str] = state.get("active_dimensions", [])
    target_company: str = state.get("target_company", "")
    all_companies: List[Dict[str, Any]] = state.get("all_companies", [])
    report_type: str = state.get("report_type", "full_analysis")
    default_template: str = state.get("default_template", "")
    references: List[str] = state.get("references", [])
    curated_ref: str = state.get("curated_ref", "")
    language: str = state.get("language", "en")

    competitor_rationale: Dict[str, Dict[str, str]] = state.get("competitor_rationale", {}) or {}
    research_scope: Dict[str, Any] = state.get("research_scope", {}) or {}
    quality_flags: List[Dict[str, Any]] = state.get("quality_flags", []) or []
    validation_report: Dict[str, Any] = state.get("validation_report", {}) or {}

    edit_mode: str = state.get("edit_mode", "")
    edit_instruction: str = state.get("edit_instruction", "")
    current_report: str = state.get("report", "")

    events: List[Dict[str, Any]] = []
    competitors = [c["name"] for c in all_companies if c["name"] != target_company]
    rt_cfg = REPORT_TYPE_CONFIGS.get(report_type, REPORT_TYPE_CONFIGS["full_analysis"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    comparisons_text, failed_dim_labels = _format_comparisons(comparisons, active_dimensions)
    battlecard_summary = _format_battlecard_summary(battlecard_data)
    references_text = _format_references(references)
    competitor_profiles_text = _format_competitor_profiles(competitor_rationale)
    data_gaps_text, low_confidence_text = _format_data_gap_confidence(dimension_evidence)
    quality_flags_text = _format_quality_flags(quality_flags, validation_report)
    market_lens, comparison_basis = _market_lens_text(research_scope)

    # Append failed-dimension notice to data_gaps so editor knows to skip them
    if failed_dim_labels:
        notice = "\n".join(
            f"- {label}: comparison unavailable (data retrieval failed; omit this section entirely)"
            for label in failed_dim_labels
        )
        data_gaps_text = f"{data_gaps_text}\n{notice}" if data_gaps_text else notice

    language_instruction = (
        "Write the full report in Chinese (Simplified Chinese)." if language == "zh"
        else "Write the full report in English."
    )

    is_edit = bool(edit_mode and current_report)
    events.append(
        {
            "type": "status",
            "node": "editor",
            "message": f"{'Editing' if is_edit else 'Compiling'} report for {target_company}",
        }
    )

    llm = _get_llm(streaming=True)
    chain = (EDITOR_EDIT_PROMPT if is_edit else EDITOR_COMPILE_PROMPT) | llm | StrOutputParser()

    common_vars = {
        "target_company": target_company,
        "competitors": ", ".join(competitors),
        "report_type_label": rt_cfg["label"],
        "research_date": today,
        "language_instruction": language_instruction,
        "market_lens": market_lens,
        "comparison_basis": comparison_basis,
        "competitor_profiles_text": competitor_profiles_text,
        "data_gaps_text": data_gaps_text,
        "low_confidence_text": low_confidence_text,
        "quality_flags_text": quality_flags_text,
    }

    if is_edit:
        invoke_vars = {
            **common_vars,
            "edit_mode": edit_mode,
            "edit_instruction": edit_instruction,
            "current_report": _normalize_text(current_report),
            "updated_comparisons": comparisons_text,
        }
    else:
        invoke_vars = {
            **common_vars,
            "template": _normalize_text(default_template),
            "comparisons_text": comparisons_text,
            "battlecard_summary": battlecard_summary,
            "references_text": references_text,
        }

    full_report = ""
    async for chunk in chain.astream(invoke_vars):
        full_report += chunk
        events.append({"type": "stream", "content": chunk, "node": "editor"})

    full_report = _normalize_text(full_report)
    events.append(
        {
            "type": "status",
            "node": "editor",
            "message": f"Report {'edited' if is_edit else 'compiled'} ({len(full_report)} chars)",
        }
    )

    if curated_ref:
        update: Dict[str, Any] = {"report": full_report}
        if is_edit:
            await mongodb_service.append_edit_history(
                curated_ref,
                edit_instruction,
                edit_mode,
                version=state.get("report_version", 0) + 1,
            )
            update["report_version"] = state.get("report_version", 0) + 1
        await mongodb_service.update_job(curated_ref, update)

    return {"report": full_report, "events": events}

