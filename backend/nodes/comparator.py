"""
Comparator node - cross-company comparison narrative per research dimension.

Outputs both:
  - comparisons: {dimension: narrative}
  - dimension_evidence: structured evidence bundle per dimension
"""

import asyncio
import logging
import os
from typing import Dict, Any, List, Tuple

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser

from backend.classes.state import CompetitorResearchState
from backend.classes.config import DIMENSION_LABELS_EN
from backend.prompts import DIMENSION_COMPARATOR_PROMPTS
from backend.services import mongodb_service

load_dotenv()
logger = logging.getLogger(__name__)

_DOC_EXCERPT_CHARS = 1_500
_DOCS_PER_COMPANY = 5
_EVIDENCE_PER_COMPANY = 3

_LLM_MAX_RETRIES = 3
_LLM_RETRY_BASE_DELAY = 2.0  # seconds, doubles each retry

# Prefix used to tag narratives that failed after all retries,
# so downstream nodes (editor) can detect and filter them.
_FAILED_PREFIX = "@@COMPARISON_FAILED@@"


def _get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.2,
        google_api_key=os.getenv("GOOGLE_API_KEY", ""),
    )


def _format_dimension_data(
    company_docs: Dict[str, List[Dict]],
    target_company: str,
    all_company_names: List[str],
    max_docs: int = _DOCS_PER_COMPANY,
    max_chars: int = _DOC_EXCERPT_CHARS,
) -> str:
    parts: List[str] = []
    ordered = [target_company] + [n for n in all_company_names if n != target_company]

    for company in ordered:
        docs = company_docs.get(company, [])
        if not docs:
            parts.append(f"### {company}\n_No data available for this dimension._")
            continue

        company_parts: List[str] = [f"### {company}"]
        for doc in docs[:max_docs]:
            title = (doc.get("title") or "Untitled").strip()
            url = doc.get("url", "")
            content = (doc.get("content") or "").strip()
            excerpt = content[:max_chars] or "_No content available._"
            published = doc.get("published_date") or "Unknown date"
            company_parts.append(f"**{title}** ({published})\n{url}\n\n{excerpt}")

        parts.append("\n\n".join(company_parts))

    return "\n\n---\n\n".join(parts) or "_No research data available._"


def _confidence_from_docs(company_docs: Dict[str, List[Dict]]) -> str:
    docs = [d for docs in company_docs.values() for d in docs]
    if not docs:
        return "low"
    scored = [float(d.get("_quality_score", d.get("score", 0.0)) or 0.0) for d in docs]
    avg = sum(scored) / max(len(scored), 1)
    if avg >= 0.7:
        return "high"
    if avg >= 0.45:
        return "medium"
    return "low"


def _collect_dimension_evidence(
    company_docs: Dict[str, List[Dict]],
    all_company_names: List[str],
) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for company in all_company_names:
        docs = company_docs.get(company, [])
        for doc in docs[:_EVIDENCE_PER_COMPANY]:
            quality = float(doc.get("_quality_score", doc.get("score", 0.0)) or 0.0)
            confidence = "high" if quality >= 0.7 else "medium" if quality >= 0.45 else "low"
            evidence.append({
                "company": company,
                "url": doc.get("url", ""),
                "title": doc.get("title", ""),
                "published_date": doc.get("published_date"),
                "excerpt": (doc.get("content") or "")[:280],
                "confidence": confidence,
            })
    return evidence


def _gap_messages(
    dimension: str,
    company_docs: Dict[str, List[Dict]],
    all_company_names: List[str],
) -> List[str]:
    gaps: List[str] = []
    for company in all_company_names:
        if len(company_docs.get(company, [])) < 2:
            gaps.append(f"Limited evidence for {company} in {dimension}.")
    if dimension == "product_pricing":
        priced = 0
        for docs in company_docs.values():
            for d in docs:
                text = f"{d.get('title','')} {d.get('content','')}".lower()
                if any(x in text for x in ("price", "$", "eur", "quote", "tier", "pricing")):
                    priced += 1
                    break
        if priced <= max(1, len(all_company_names) // 2):
            gaps.append("Public pricing evidence is sparse across competitors.")
    return gaps


def _rationale_text(competitor_rationale: Dict[str, Dict[str, str]]) -> str:
    if not competitor_rationale:
        return "No explicit competitor rationale provided."
    lines: List[str] = []
    for name, payload in competitor_rationale.items():
        why = (
            payload.get("why_included", "").strip()
            or payload.get("reason", "").strip()
            or "No rationale provided."
        )
        threat = payload.get("threat_type", "direct_competitor")
        lines.append(f"- {name}: {why} (threat_type={threat})")
    return "\n".join(lines)


async def _compare_one_dimension(
    dimension: str,
    company_docs: Dict[str, List[Dict]],
    target_company: str,
    all_company_names: List[str],
    competitors: List[str],
    comparator_focus: str,
    competitor_rationale_text: str,
    comparison_basis: str,
) -> Tuple[str, str]:
    prompt = DIMENSION_COMPARATOR_PROMPTS.get(dimension)
    if not prompt:
        return dimension, f"{_FAILED_PREFIX}_No comparator prompt configured for: {dimension}_"

    dimension_data = _format_dimension_data(company_docs, target_company, all_company_names)
    label = DIMENSION_LABELS_EN.get(dimension, dimension)

    last_exc: Exception | None = None
    for attempt in range(1, _LLM_MAX_RETRIES + 1):
        try:
            llm = _get_llm()
            chain = prompt | llm | StrOutputParser()
            narrative = await chain.ainvoke({
                "target_company": target_company,
                "competitors": ", ".join(competitors),
                "comparator_focus": comparator_focus,
                "dimension_data": dimension_data,
                "comparison_basis": comparison_basis,
                "competitor_rationale_text": competitor_rationale_text,
            })
            text = (narrative or "").strip()
            if not text:
                return dimension, f"{_FAILED_PREFIX}_Comparison returned empty for {label}._"
            if attempt > 1:
                logger.info("comparator succeeded dimension=%s on attempt %d", dimension, attempt)
            return dimension, text
        except Exception as exc:
            last_exc = exc
            if attempt < _LLM_MAX_RETRIES:
                delay = _LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "comparator attempt %d/%d failed dimension=%s: %s — retrying in %.1fs",
                    attempt, _LLM_MAX_RETRIES, dimension, exc, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "comparator exhausted %d retries dimension=%s target=%s",
                    _LLM_MAX_RETRIES, dimension, target_company, exc_info=True,
                )

    msg = str(last_exc) or f"{type(last_exc).__name__} (no message)"
    return dimension, f"{_FAILED_PREFIX}_Comparison failed for {label}: {msg}_"


async def comparator_node(state: CompetitorResearchState) -> Dict[str, Any]:
    active_dimensions: List[str] = state.get("active_dimensions", [])
    target_company: str = state.get("target_company", "")
    all_companies: List[Dict] = state.get("all_companies", [])
    comparator_focus: str = state.get("comparator_focus", "")
    curated_ref: str = state.get("curated_ref", "")
    competitor_rationale = state.get("competitor_rationale", {}) or {}
    research_scope = state.get("research_scope", {}) or {}

    all_company_names: List[str] = [c["name"] for c in all_companies]
    competitors: List[str] = [n for n in all_company_names if n != target_company]
    comparison_basis = research_scope.get(
        "comparison_basis",
        "Compare companies on selected report dimensions and call out weak evidence.",
    )
    rationale_text = _rationale_text(competitor_rationale)

    events: List[Dict] = [{
        "type": "status",
        "node": "comparator",
        "message": (
            f"Comparing {len(active_dimensions)} dimensions in parallel - "
            f"{target_company} vs {len(competitors)} competitor(s)"
        ),
    }]

    dim_data_tasks = [
        mongodb_service.get_dimension_data(curated_ref, dim, all_company_names)
        for dim in active_dimensions
    ]
    dim_data_results = await asyncio.gather(*dim_data_tasks, return_exceptions=True)

    dimension_company_docs: Dict[str, Dict[str, List[Dict]]] = {}
    for dim, result in zip(active_dimensions, dim_data_results):
        if isinstance(result, Exception):
            dimension_company_docs[dim] = {}
            events.append({
                "type": "status",
                "node": "comparator",
                "dimension": dim,
                "message": f"MongoDB load failed for {dim}: {result}",
            })
        else:
            dimension_company_docs[dim] = result

    comparison_tasks = [
        _compare_one_dimension(
            dimension=dim,
            company_docs=dimension_company_docs.get(dim, {}),
            target_company=target_company,
            all_company_names=all_company_names,
            competitors=competitors,
            comparator_focus=comparator_focus,
            competitor_rationale_text=rationale_text,
            comparison_basis=comparison_basis,
        )
        for dim in active_dimensions
    ]
    raw_results = await asyncio.gather(*comparison_tasks, return_exceptions=True)

    comparisons: Dict[str, str] = {}
    dimension_evidence: Dict[str, Dict[str, Any]] = {}
    for result in raw_results:
        if isinstance(result, Exception):
            events.append({
                "type": "status",
                "node": "comparator",
                "message": f"Comparison task raised: {result}",
            })
            continue
        dim, narrative = result
        comparisons[dim] = narrative

        docs = dimension_company_docs.get(dim, {})
        evidence = _collect_dimension_evidence(docs, all_company_names)
        gaps = _gap_messages(dim, docs, all_company_names)
        confidence = _confidence_from_docs(docs)
        dimension_evidence[dim] = {
            "narrative": narrative,
            "confidence": confidence,
            "data_gaps": gaps,
            "evidence": evidence,
            "comparison_basis": comparison_basis,
        }

        label = DIMENSION_LABELS_EN.get(dim, dim)
        events.append({
            "type": "status",
            "node": "comparator",
            "dimension": dim,
            "message": (
                f"{label}: {len(narrative)} chars, "
                f"confidence={confidence}, evidence={len(evidence)}"
            ),
        })

    if curated_ref and comparisons:
        await mongodb_service.update_job(
            curated_ref,
            {
                "comparisons": comparisons,
                "dimension_evidence": dimension_evidence,
                "competitor_rationale": competitor_rationale,
                "research_scope": research_scope,
            },
        )

    events.append({
        "type": "status",
        "node": "comparator",
        "message": f"Comparator complete - {len(comparisons)}/{len(active_dimensions)} dimensions written",
    })

    return {
        "comparisons": comparisons,
        "dimension_evidence": dimension_evidence,
        "events": events,
    }
