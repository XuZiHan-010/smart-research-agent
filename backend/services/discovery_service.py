"""
Discovery Service — auto-discover competitor companies via Exa.

Called by the FastAPI /discover endpoint BEFORE the LangGraph pipeline starts.
This is intentionally NOT a LangGraph node because:
  - Discovery requires user confirmation (async round-trip with the frontend)
  - Making it a pure service function keeps the graph simpler and stateless

Flow (new — Level 1: Exa real-time articles + LLM extraction):
  1. User submits {target_company, target_website, competitors: [0–3 names]}
  2. API calls discover_competitors()
  3. Exa searches recent (12-month) news/analysis articles for competitor mentions
  4. GPT-4.1-mini extracts competitor names from the article context
  5. Exa looks up the official URL for each name (two-phase: with/without category)
  6. Returns [{name, website, score, default_checked}] for the frontend
     confirmation panel (DiscoveryPanel component)

Fallback path (legacy):
  If Exa news search + LLM extraction fails or returns empty, falls back to the
  original direct Exa neural search to avoid complete failure.

Scenarios handled:
  0 competitors provided  → full auto-discover, all suggestions default_checked=True
  1–3 competitors         → supplement with auto-discover to reach up to 5 total
  4–5 competitors         → skipped (caller should not call this endpoint)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from exa_py import Exa
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

logger = logging.getLogger(__name__)

_MAX_SUGGESTIONS   = 5      # max auto-discovered suggestions returned
_SEARCH_RESULTS    = 8      # Exa results per query (legacy fallback)
_PER_QUERY_RESULTS = 6      # Exa news results per variant query
_NEWS_MONTHS       = 12     # look-back window in months for news search

# Query variants fanned out in parallel for higher recall on diversified conglomerates.
# Pattern adopted from C:\Users\Penguin\.claude\skills\company-research (query variation).
_NEWS_QUERY_VARIANTS = [
    "{target} competitors alternatives {year}",
    "{target} vs industry rivals market leaders {year}",
    "companies competing with {target} in same market",
]


def _get_exa() -> Exa:
    return Exa(api_key=os.getenv("EXA_API_KEY", "").strip())


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0.1,
        api_key=os.getenv("OPENAI_API_KEY", ""),
    )


def _parse_json_list(raw: str) -> List[Dict[str, Any]]:
    """
    Parse LLM JSON output into a list. Handles markdown fences.
    Returns [] on any parse error.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end   = -1 if lines[-1].strip() == "```" else len(lines)
        text  = "\n".join(lines[1:end])
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        return []
    except json.JSONDecodeError:
        return []


def _extract_company_name(result: Any, fallback_url: str) -> str:
    """
    Best-effort company name from an Exa search result.
    Priority: result.title → domain stem from URL
    """
    title = getattr(result, "title", "") or ""
    if title.strip():
        # Strip boilerplate suffixes: "Acme | Home", "Acme - Products", etc.
        for sep in [" | ", " - ", " — ", " · ", ": "]:
            if sep in title:
                title = title.split(sep)[0]
        return title.strip()

    # Fall back to domain stem
    domain = urlparse(fallback_url).netloc.lstrip("www.")
    name   = domain.split(".")[0].replace("-", " ").title()
    return name


def _infer_threat_type(reason: str) -> str:
    text = (reason or "").lower()
    if any(k in text for k in ["channel", "distribution", "partner ecosystem"]):
        return "channel_threat"
    if any(k in text for k in ["adjacent", "overlap", "substitute"]):
        return "adjacent_threat"
    if any(k in text for k in ["emerging", "startup", "new entrant"]):
        return "emerging_threat"
    return "direct_competitor"


# ── New path helpers ───────────────────────────────────────────────────────────

async def _single_news_search(
    exa:   Exa,
    query: str,
    since: str,
) -> List[Any]:
    """Run a single Exa news search for one query variant."""
    loop = asyncio.get_event_loop()
    try:
        resp = await loop.run_in_executor(
            None,
            lambda: exa.search_and_contents(
                query,
                num_results=_PER_QUERY_RESULTS,
                type="neural",
                category="news",
                start_published_date=since,
                text=True,
            ),
        )
        return list(resp.results)
    except Exception:
        logger.warning("news_search variant failed query=%r", query, exc_info=True)
        return []


async def _exa_fetch_recent_articles(
    exa:            Exa,
    target_company: str,
) -> str:
    """
    Search Exa for recent news/analysis articles about competitors of target_company.
    Fans out 3 query variants in parallel (query variation pattern) and merges/dedupes by URL.
    Uses a 12-month look-back window so results reflect 2025 market state.
    Returns a single string of concatenated article snippets for LLM context.
    """
    since = (
        datetime.now(timezone.utc) - timedelta(days=_NEWS_MONTHS * 30)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    now_year = datetime.now(timezone.utc).year
    queries = [q.format(target=target_company, year=now_year) for q in _NEWS_QUERY_VARIANTS]
    batches = await asyncio.gather(
        *[_single_news_search(exa, q, since) for q in queries]
    )

    # Merge + dedupe by URL, preserving first occurrence
    seen_urls: set = set()
    snippets:  List[str] = []
    for batch in batches:
        for r in batch:
            url = getattr(r, "url", "") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = getattr(r, "title", "") or ""
            text  = (getattr(r, "text", "") or "")[:500]
            if text:
                snippets.append(f"[{title}] ({url})\n{text}")

    logger.info(
        "news_search target=%s queries=%d unique_articles=%d",
        target_company, len(queries), len(snippets),
    )
    return "\n\n---\n\n".join(snippets)


async def _llm_extract_competitors(
    target_company:   str,
    articles_context: str,
    existing_names:   List[str],
    max_names:        int = 8,
) -> List[str]:
    """
    Use GPT-4.1-mini to extract competitor company names from Exa news articles.
    When no articles are available, falls back to LLM's own knowledge.
    Returns a list of company name strings.
    """
    existing_str = ", ".join(existing_names) if existing_names else "none"
    context_section = (
        f"RECENT ARTICLES (use these as your primary source):\n{articles_context}"
        if articles_context
        else "(No recent articles found — use your training knowledge)"
    )
    prompt = f"""You are a competitive intelligence analyst.

{context_section}

TASK: Identify the top {max_names} direct competitors of {target_company}.

RULES:
- Exclude these already-known companies: {existing_str}
- Exclude {target_company} itself
- Focus on companies that compete in the SAME core markets/products/services
- For each competitor, include a brief reason explaining the competitive overlap (1 sentence)
- Return ONLY a JSON array, no explanation text outside the array

REQUIRED FORMAT:
[{{"name": "CompanyName", "reason": "Reason for competition"}}, ...]"""

    llm   = _get_llm()
    chain = llm | StrOutputParser()

    try:
        raw   = await chain.ainvoke(prompt)
        items = _parse_json_list(raw)
        if not items:
            logger.warning(
                "llm_extract returned empty/unparsable JSON raw=%r",
                raw[:300] if isinstance(raw, str) else raw,
            )
        candidates = []
        for item in items:
            if isinstance(item, dict) and "name" in item:
                name = str(item["name"]).strip()
                reason = str(item.get("reason", "")).strip()
                if name:
                    candidates.append({"name": name, "reason": reason})
            elif isinstance(item, str) and item.strip():
                candidates.append({"name": item.strip(), "reason": ""})
        return candidates
    except Exception:
        logger.warning("llm_extract_competitors failed", exc_info=True)
        return []


async def _exa_lookup_url(
    exa:          Exa,
    company_name: str,
) -> Optional[Dict[str, str]]:
    """
    Find the official website URL for a company name.
    Two-phase search:
      Phase 1: category="company" for precise homepage results
      Phase 2: no category filter (fallback if Exa mis-classifies the company)
    Returns {name, website} or None if both phases fail.
    """
    query = f'"{company_name}" official website'
    loop  = asyncio.get_event_loop()

    async def _run_search(use_category: bool) -> Optional[str]:
        try:
            kwargs: Dict[str, Any] = {
                "num_results": 1,
                "type":        "neural",
            }
            if use_category:
                kwargs["category"] = "company"
            resp = await loop.run_in_executor(
                None,
                lambda: exa.search(query, **kwargs),
            )
            if resp.results:
                url = getattr(resp.results[0], "url", None)
                return url if url else None
        except Exception:
            logger.warning(
                "exa_lookup_url failed name=%r category=%s",
                company_name, use_category, exc_info=True,
            )
        return None

    url = await _run_search(use_category=True)
    if not url:
        url = await _run_search(use_category=False)
    if not url:
        return None
    return {"name": company_name, "website": url}


# ── Legacy fallback ────────────────────────────────────────────────────────────

async def _search_once(
    exa:   Exa,
    query: str,
    n:     int = _SEARCH_RESULTS,
) -> List[Any]:
    """Run a single Exa company search in a thread executor (sync SDK). Legacy fallback."""
    loop = asyncio.get_event_loop()
    try:
        resp = await loop.run_in_executor(
            None,
            lambda: exa.search(
                query,
                num_results=n,
                type="neural",
                category="company",
            ),
        )
        return resp.results
    except Exception:
        return []


# ── Main entry point ───────────────────────────────────────────────────────────

async def discover_competitors(
    target_company:   str,
    target_website:   str = "",
    existing_names:   Optional[List[str]] = None,
    max_suggestions:  int = _MAX_SUGGESTIONS,
) -> List[Dict[str, Any]]:
    """
    Auto-discover competitor companies for `target_company`.

    Args:
        target_company:  The company being analysed.
        target_website:  Its official URL (used to exclude it from results).
        existing_names:  Competitor names the user already entered — excluded.
        max_suggestions: Max items in the returned list.

    Returns:
        List of dicts:  {name, website, score, default_checked}
    """
    existing_names = existing_names or []
    exa = _get_exa()

    excluded_names: set = {n.lower().strip() for n in existing_names}
    excluded_names.add(target_company.lower().strip())
    excluded_domains: set = set()
    if target_website:
        excluded_domains.add(urlparse(target_website).netloc.lstrip("www.").lower())

    # ── PRIMARY PATH: Exa real-time articles → LLM extraction → Exa URL lookup ──
    try:
        articles_context = await _exa_fetch_recent_articles(exa, target_company)
        logger.info("discover step1a articles_chars=%d", len(articles_context))

        candidates = await _llm_extract_competitors(
            target_company,
            articles_context,
            existing_names,
            max_names=max_suggestions + 3,  # request a few extra in case some URLs fail
        )
        # Filter out any name already excluded
        candidates = [
            c for c in candidates
            if c["name"].lower().strip() not in excluded_names
        ]
        logger.info("discover step1b candidates=%s", [c["name"] for c in candidates])

        # Build a name→reason lookup for later
        reason_map = {c["name"].lower().strip(): c["reason"] for c in candidates}

        if candidates:
            # Concurrent URL lookup for all candidates
            url_results = await asyncio.gather(
                *[_exa_lookup_url(exa, c["name"]) for c in candidates]
            )
            found = [r for r in url_results if r is not None]
            logger.info(
                "discover step2 urls_found=%d/%d",
                len(found), len(candidates),
            )

            suggestions: List[Dict[str, Any]] = []
            seen_domains: set = set()

            for item in url_results:
                if item is None:
                    continue
                name   = item["name"]
                url    = item["website"]
                domain = urlparse(url).netloc.lstrip("www.").lower()

                if domain in excluded_domains or domain in seen_domains:
                    continue
                if name.lower().strip() in excluded_names:
                    continue

                seen_domains.add(domain)
                suggestions.append({
                    "name":            name,
                    "website":         url,
                    "reason":          reason_map.get(name.lower().strip(), ""),
                    "threat_type":     _infer_threat_type(reason_map.get(name.lower().strip(), "")),
                    "score":           1.0,
                    "default_checked": True,
                })

                if len(suggestions) >= max_suggestions:
                    break

            logger.info("discover step3 suggestions=%d", len(suggestions))
            if suggestions:
                return suggestions
            logger.warning(
                "discover primary path returned 0 suggestions after URL lookup, falling back to legacy"
            )
        else:
            logger.warning(
                "discover primary path: no candidate names extracted, falling back to legacy"
            )

    except Exception:
        logger.warning("discover primary path raised unexpectedly", exc_info=True)

    # ── LEGACY FALLBACK: original Exa direct neural search ────────────────────
    queries = [
        f"{target_company} top competitors alternatives",
        f"companies competing with {target_company} in same market",
    ]
    raw_batches = await asyncio.gather(*[_search_once(exa, q) for q in queries])

    seen_domains_legacy: Dict[str, float] = {}
    candidates_legacy:   Dict[str, Dict]  = {}

    for batch in raw_batches:
        for r in batch:
            url    = getattr(r, "url", "") or ""
            score  = float(getattr(r, "score", 0.0))
            domain = urlparse(url).netloc.lstrip("www.").lower()
            name   = _extract_company_name(r, url)

            if domain in excluded_domains:
                continue
            if name.lower().strip() in excluded_names:
                continue
            if len(name.strip()) < 2:
                continue

            if domain not in seen_domains_legacy or score > seen_domains_legacy[domain]:
                seen_domains_legacy[domain] = score
                candidates_legacy[domain] = {
                    "name":            name,
                    "website":         url,
                    "reason":          "",
                    "threat_type":     "direct_competitor",
                    "score":           round(score, 4),
                    "default_checked": True,
                }

    sorted_candidates = sorted(
        candidates_legacy.values(),
        key=lambda x: x["score"],
        reverse=True,
    )
    result = sorted_candidates[:max_suggestions]
    logger.info("discover legacy returned=%d", len(result))
    return result
