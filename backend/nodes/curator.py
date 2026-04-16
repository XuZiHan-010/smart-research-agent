"""
Curator node — scores, filters, enriches, and persists research documents.

Pipeline per (company, dimension) pair:
  1. Score   — multi-factor quality score (Exa base + domain authority + recency)
  2. Filter  — drop docs below EXA_SCORE_THRESHOLD
  3. Sort    — descending by quality score
  4. Cap     — keep at most max_docs_per_dim docs
  5. Enrich  — batch-fetch full text via exa.get_contents()
  6. Persist — write curated_company_data to MongoDB (NOT to State)

Returns:
  curated_ref    — job_id string (State pointer to MongoDB data)
  references     — deduplicated top-domain URL list for report Sources section
  curation_stats — summary counts for evaluator gate
  events         — progress events

Why content lives in MongoDB, not State:
  N companies × M dimensions × max_docs_per_dim docs × 4000 chars/doc
  can exceed 1 MB for deep_dive jobs. LangGraph State is checkpointed on
  every node; keeping only a job_id pointer cuts State size ~95%.
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from urllib.parse import urlparse

from dotenv import load_dotenv
from exa_py import Exa

from backend.classes.state import CompetitorResearchState
from backend.classes.config import (
    EXA_SCORE_THRESHOLD,
    EXA_BATCH_SIZE,
    DOC_MAX_CHARS,
    REFERENCES_MAX,
    AUTHORITATIVE_DOMAINS,
    STALE_DATA_DAYS,
    DIMENSION_LABELS_EN,
)
from backend.services import mongodb_service

load_dotenv()

_exa_client = None


def _get_exa() -> Exa:
    global _exa_client
    if _exa_client is None:
        _exa_client = Exa(api_key=os.getenv("EXA_API_KEY", ""))
    return _exa_client


# ── Quality scoring ───────────────────────────────────────────────────────────

_RECENCY_SENSITIVE = {"recent_activity", "traction_growth"}


def _quality_score(doc: Dict, dimension: str) -> float:
    """
    Multi-factor quality score in [0, 1.15] range.

    Base:       Exa neural score (already in [0, 1])
    +0.15       if URL domain is authoritative for this dimension
    -0.10       if title is very short (< 10 chars) — likely low-quality
    -0.10       if document is stale (> STALE_DATA_DAYS) for recency-sensitive dims
    """
    score = float(doc.get("score", 0.0))

    # Domain authority boost
    url    = doc.get("url", "")
    domain = urlparse(url).netloc.lower().lstrip("www.")
    auth_domains = AUTHORITATIVE_DOMAINS.get(dimension, [])
    if any(auth in domain for auth in auth_domains):
        score += 0.15

    # Short-title penalty
    title = doc.get("title", "") or ""
    if len(title.strip()) < 10:
        score -= 0.10

    # Staleness penalty for recency-sensitive dimensions
    if dimension in _RECENCY_SENSITIVE:
        pub_date = doc.get("published_date") or doc.get("publishedDate")
        if pub_date:
            try:
                if isinstance(pub_date, str):
                    pub_dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                else:
                    pub_dt = pub_date
                now = datetime.now(timezone.utc)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                age_days = (now - pub_dt).days
                if age_days > STALE_DATA_DAYS:
                    score -= 0.10
            except (ValueError, TypeError):
                pass

    return score


# ── Content fetching ──────────────────────────────────────────────────────────

async def _fetch_contents(urls: List[str]) -> Dict[str, str]:
    """Batch-fetch full text for a list of URLs via Exa get_contents."""
    if not urls:
        return {}

    exa    = _get_exa()
    result: Dict[str, str] = {}

    async def _fetch_batch(batch: List[str]) -> Dict[str, str]:
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: exa.get_contents(
                    batch,
                    text={"max_characters": DOC_MAX_CHARS, "include_html_tags": False},
                ),
            )
            return {r.url: (r.text or "") for r in response.results if r.url}
        except Exception:
            return {}

    batches      = [urls[i:i + EXA_BATCH_SIZE] for i in range(0, len(urls), EXA_BATCH_SIZE)]
    batch_results = await asyncio.gather(*[_fetch_batch(b) for b in batches])
    for br in batch_results:
        result.update(br)

    return result


# ── Reference builder ─────────────────────────────────────────────────────────

def _build_references(
    curated_by_company: Dict[str, Dict[str, List[Dict]]],
    max_refs: int = REFERENCES_MAX,
) -> List[str]:
    """
    Collect top-scored unique-domain URLs across all companies and dimensions.
    Returns a flat list of up to max_refs markdown-formatted references
    (``[title](url)``) for the report Sources section.
    """
    all_docs: List[Tuple[float, str, str]] = []
    for dim_data in curated_by_company.values():
        for docs in dim_data.values():
            for doc in docs:
                score = doc.get("_quality_score", doc.get("score", 0))
                url   = doc.get("url", "")
                title = doc.get("title", "") or ""
                if url:
                    all_docs.append((score, url, title))

    all_docs.sort(key=lambda x: x[0], reverse=True)

    seen_domains: set = set()
    references: List[str] = []
    for _, url, title in all_docs:
        domain = urlparse(url).netloc.lower().lstrip("www.")
        if domain not in seen_domains:
            seen_domains.add(domain)
            label = title.strip() if title.strip() else domain
            references.append(f"[{label}]({url})")
        if len(references) >= max_refs:
            break

    return references


# ── Node entry point ──────────────────────────────────────────────────────────

async def curator_node(state: CompetitorResearchState) -> Dict[str, Any]:
    """LangGraph node: curate research_results and persist to MongoDB."""

    research_results: List[Dict] = state.get("research_results", [])
    max_docs_per_dim: int        = state.get("max_docs_per_dim", 15)
    job_id: str                  = state.get("job_id", "")
    all_companies: List[Dict]    = state.get("all_companies", [])

    events: List[Dict] = []

    if not research_results:
        return {
            "curated_ref":    job_id,
            "references":     [],
            "curation_stats": {"total_docs_in": 0, "total_docs_out": 0},
            "events": [{
                "type": "status", "node": "curator",
                "message": "No research results to curate — skipping",
            }],
        }

    # ── Group research_results by company → dimension → docs ─────────────────
    # research_results is List[ResearchResultDict]; each has:
    #   company, dimension, docs (list of {url, title, score, ...}), status
    grouped: Dict[str, Dict[str, List[Dict]]] = {}
    for result in research_results:
        company   = result.get("company", "unknown")
        dimension = result.get("dimension", "unknown")
        docs      = result.get("docs", [])
        grouped.setdefault(company, {}).setdefault(dimension, [])
        grouped[company][dimension].extend(docs)

    total_docs_in = sum(
        len(docs)
        for dim_data in grouped.values()
        for docs in dim_data.values()
    )

    events.append({
        "type":    "status",
        "node":    "curator",
        "message": f"Curating {total_docs_in} raw docs across {len(grouped)} companies",
    })

    # ── Score → filter → sort → cap per (company, dimension) ─────────────────
    curated_by_company: Dict[str, Dict[str, List[Dict]]] = {}
    all_urls_to_fetch: List[str] = []

    for company, dim_data in grouped.items():
        curated_by_company[company] = {}
        for dimension, docs in dim_data.items():
            scored = []
            for doc in docs:
                qs = _quality_score(doc, dimension)
                if qs >= EXA_SCORE_THRESHOLD:
                    enriched = dict(doc)
                    enriched["_quality_score"] = round(qs, 4)
                    scored.append(enriched)

            scored.sort(key=lambda d: d["_quality_score"], reverse=True)
            capped = scored[:max_docs_per_dim]
            curated_by_company[company][dimension] = capped
            all_urls_to_fetch.extend(d["url"] for d in capped if d.get("url"))

    # deduplicate URLs before fetching
    unique_urls = list(dict.fromkeys(all_urls_to_fetch))

    # ── Batch-fetch full content ───────────────────────────────────────────────
    events.append({
        "type":    "status",
        "node":    "curator",
        "message": f"Fetching full content for {len(unique_urls)} unique URLs",
    })

    content_map: Dict[str, str] = await _fetch_contents(unique_urls)

    # Merge content into curated docs
    total_docs_out = 0
    dim_stats: Dict[str, Dict[str, int]] = {}  # {dimension: {company: count}}

    for company, dim_data in curated_by_company.items():
        for dimension, docs in dim_data.items():
            for doc in docs:
                url = doc.get("url", "")
                if url in content_map:
                    doc["content"] = content_map[url]
                else:
                    doc["content"] = ""
            total_docs_out += len(docs)
            dim_stats.setdefault(dimension, {})[company] = len(docs)

            label = DIMENSION_LABELS_EN.get(dimension, dimension)
            events.append({
                "type":      "status",
                "node":      "curator",
                "company":   company,
                "dimension": dimension,
                "message":   f"{company} / {label}: {len(docs)} docs curated",
            })

    # ── Persist to MongoDB ────────────────────────────────────────────────────
    if job_id:
        await mongodb_service.update_job(job_id, {
            "curated_company_data": curated_by_company,
        })

    # ── Build references list ─────────────────────────────────────────────────
    references = _build_references(curated_by_company)

    # ── Curation stats for Evaluator ─────────────────────────────────────────
    company_names = [c["name"] for c in all_companies]
    curation_stats = {
        "total_docs_in":  total_docs_in,
        "total_docs_out": total_docs_out,
        "companies":      company_names,
        "dim_stats":      dim_stats,   # {dimension: {company: doc_count}}
    }

    events.append({
        "type":    "status",
        "node":    "curator",
        "message": (
            f"Curation complete — {total_docs_in} in, {total_docs_out} out, "
            f"{len(references)} references"
        ),
    })

    return {
        "curated_ref":    job_id,
        "references":     references,
        "curation_stats": curation_stats,
        "events":         events,
    }
