"""
Battlecard builder node.

Builds structured battlecard JSON from comparison narratives and evidence bundle.
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, List

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

from backend.classes.state import CompetitorResearchState
from backend.classes.config import DIMENSION_LABELS_EN
from backend.prompts import BATTLECARD_PROMPT
from backend.services import mongodb_service

load_dotenv()

_COMPARISONS_MAX_CHARS = 30_000


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key=os.getenv("OPENAI_API_KEY", ""),
    )


def _bundle_comparisons(
    comparisons: Dict[str, str],
    active_dimensions: List[str],
    max_chars: int = _COMPARISONS_MAX_CHARS,
) -> str:
    budget = max_chars // max(len(comparisons), 1)
    parts: List[str] = []
    for dim in active_dimensions:
        narrative = comparisons.get(dim, "")
        if not narrative:
            continue
        label = DIMENSION_LABELS_EN.get(dim, dim)
        parts.append(f"## {label}\n\n{narrative[:budget]}")
    return "\n\n---\n\n".join(parts) or "No comparison data available."


def _parse_json(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        return {
            "parse_error": str(exc),
            "raw_response": raw[:2_000],
        }


def _dimension_confidence_summary(dimension_evidence: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    return {
        dim: str(payload.get("confidence", "low"))
        for dim, payload in dimension_evidence.items()
    }


def _flatten_data_gaps(dimension_evidence: Dict[str, Dict[str, Any]]) -> List[str]:
    gaps: List[str] = []
    for payload in dimension_evidence.values():
        for msg in payload.get("data_gaps", []) or []:
            if msg not in gaps:
                gaps.append(msg)
    return gaps


def _competitor_profiles(
    competitors: List[str],
    competitor_rationale: Dict[str, Dict[str, str]],
) -> List[Dict[str, str]]:
    profiles: List[Dict[str, str]] = []
    for name in competitors:
        meta = competitor_rationale.get(name, {})
        profiles.append({
            "name": name,
            "rationale": (
                meta.get("why_included", "")
                or meta.get("reason", "")
                or "Selected as relevant competitor."
            ),
            "threat_type": meta.get("threat_type", "direct_competitor"),
        })
    return profiles


async def battlecard_builder_node(state: CompetitorResearchState) -> Dict[str, Any]:
    comparisons: Dict[str, str] = state.get("comparisons", {})
    dimension_evidence: Dict[str, Dict[str, Any]] = state.get("dimension_evidence", {})
    active_dimensions: List[str] = state.get("active_dimensions", [])
    target_company: str = state.get("target_company", "")
    all_companies: List[Dict] = state.get("all_companies", [])
    curated_ref: str = state.get("curated_ref", "")
    competitor_rationale = state.get("competitor_rationale", {}) or {}

    competitors = [c["name"] for c in all_companies if c["name"] != target_company]
    events: List[Dict] = [{
        "type": "status",
        "node": "battlecard_builder",
        "message": f"Building battlecard for {target_company} vs {len(competitors)} competitor(s)",
    }]

    if not comparisons:
        battlecard: Dict[str, Any] = {
            "target": target_company,
            "competitors": competitors,
            "competitor_profiles": _competitor_profiles(competitors, competitor_rationale),
            "feature_matrix": [],
            "pricing_comparison": [],
            "win_themes": [],
            "lose_themes": [],
            "key_risks": [],
            "objection_handlers": [],
            "confidence_summary": _dimension_confidence_summary(dimension_evidence),
            "data_gaps": _flatten_data_gaps(dimension_evidence),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parse_error": "No comparison data - battlecard could not be built",
        }
        events.append({
            "type": "status",
            "node": "battlecard_builder",
            "message": "No comparisons available - returning empty battlecard",
        })
        return {"battlecard_data": battlecard, "events": events}

    comparisons_text = _bundle_comparisons(comparisons, active_dimensions)
    evidence_text = json.dumps(dimension_evidence, ensure_ascii=False)[:24_000]
    rationale_text = json.dumps(competitor_rationale, ensure_ascii=False)

    llm = _get_llm()
    chain = BATTLECARD_PROMPT | llm | StrOutputParser()

    try:
        raw = await chain.ainvoke({
            "target_company": target_company,
            "competitors": ", ".join(competitors),
            "competitors_json": json.dumps(competitors, ensure_ascii=False),
            "comparisons_text": comparisons_text,
            "dimension_evidence": evidence_text,
            "competitor_rationale_text": rationale_text,
        })
        battlecard = _parse_json(raw)
    except Exception as exc:
        battlecard = {
            "target": target_company,
            "competitors": competitors,
            "parse_error": str(exc),
        }
        events.append({
            "type": "status",
            "node": "battlecard_builder",
            "message": f"LLM call failed: {exc}",
        })

    battlecard["target"] = target_company
    battlecard["competitors"] = battlecard.get("competitors") or competitors
    battlecard["competitor_profiles"] = (
        battlecard.get("competitor_profiles")
        or _competitor_profiles(competitors, competitor_rationale)
    )
    battlecard["confidence_summary"] = (
        battlecard.get("confidence_summary")
        or _dimension_confidence_summary(dimension_evidence)
    )
    battlecard["data_gaps"] = battlecard.get("data_gaps") or _flatten_data_gaps(dimension_evidence)
    battlecard["generated_at"] = datetime.now(timezone.utc).isoformat()

    if curated_ref:
        await mongodb_service.update_job(curated_ref, {"battlecard_data": battlecard})

    has_error = "parse_error" in battlecard
    events.append({
        "type": "status",
        "node": "battlecard_builder",
        "message": (
            f"Battlecard {'failed (parse error)' if has_error else 'built'} - "
            f"{len(battlecard.get('feature_matrix', []))} features, "
            f"{len(battlecard.get('win_themes', []))} win themes, "
            f"{len(battlecard.get('lose_themes', []))} lose themes"
        ),
    })

    return {"battlecard_data": battlecard, "events": events}
