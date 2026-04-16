"""
Grounding node — crawls each company's official website in parallel.

For every company in all_companies:
  1. If a website URL is provided → crawl it directly
  2. If no URL → search Exa for the official site first, then crawl

Output:
  site_scrapes: {company_name: crawled_text (max GROUNDING_MAX_CHARS chars)}

Design notes:
  - Semaphore(SEMAPHORE_GROUNDING) caps parallel HTTP requests
  - Failures are soft: missing scrape becomes empty string, pipeline continues
  - Content is capped at GROUNDING_MAX_CHARS; researchers only use the first
    GROUNDING_QUERY_CHARS chars for query generation
"""

import asyncio
import os
from typing import Dict, Any, List

from dotenv import load_dotenv
from exa_py import Exa

from backend.classes.state import CompetitorResearchState
from backend.classes.config import (
    GROUNDING_MAX_CHARS,
    SEMAPHORE_GROUNDING,
)

load_dotenv()

_exa_client = None


def _get_exa() -> Exa:
    global _exa_client
    if _exa_client is None:
        _exa_client = Exa(api_key=os.getenv("EXA_API_KEY", ""))
    return _exa_client


async def _scrape_url(exa: Exa, url: str) -> str:
    """Fetch and clean text from a single URL via Exa get_contents."""
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: exa.get_contents(
                [url],
                text={"max_characters": GROUNDING_MAX_CHARS, "include_html_tags": False},
                highlights={"num_sentences": 8, "highlights_per_url": 2},
            ),
        )
        if not result.results:
            return ""
        r    = result.results[0]
        text = r.text or ""
        if getattr(r, "highlights", None):
            text = "\n".join(r.highlights) + "\n\n" + text
        return text[:GROUNDING_MAX_CHARS]
    except Exception:
        return ""


async def _find_and_scrape(exa: Exa, company_name: str) -> str:
    """Search Exa for the official site then scrape it."""
    loop = asyncio.get_event_loop()
    try:
        search_result = await loop.run_in_executor(
            None,
            lambda: exa.search(
                f'"{company_name}" official website',
                num_results=1,
                type="neural",
            ),
        )
        if not search_result.results:
            return ""
        url = search_result.results[0].url
        return await _scrape_url(exa, url)
    except Exception:
        return ""


async def _ground_one_company(
    semaphore: asyncio.Semaphore,
    exa: Exa,
    company: Dict[str, str],
) -> tuple:
    """
    Returns (company_name, site_scrape_text, event_message).
    Never raises — failures become empty strings.
    """
    name    = company["name"]
    website = company.get("website", "").strip()

    async with semaphore:
        if website:
            text   = await _scrape_url(exa, website)
            source = website
        else:
            text   = await _find_and_scrape(exa, name)
            source = "auto-discovered" if text else "not found"

    if text:
        msg = f"Grounded {name}: {len(text)} chars from {source}"
    else:
        msg = f"Grounding failed for {name} — will continue without site content"

    return name, text, msg


async def grounding_node(state: CompetitorResearchState) -> Dict[str, Any]:
    """LangGraph node: parallel website crawl for all companies."""
    all_companies: List[Dict[str, str]] = state.get("all_companies", [])

    if not all_companies:
        return {
            "site_scrapes": {},
            "events": [{"type": "status", "node": "grounding",
                        "message": "No companies to ground — skipping"}],
        }

    exa       = _get_exa()
    semaphore = asyncio.Semaphore(SEMAPHORE_GROUNDING)

    tasks   = [_ground_one_company(semaphore, exa, c) for c in all_companies]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    site_scrapes: Dict[str, str] = {}
    events: List[Dict] = []

    for r in results:
        if isinstance(r, Exception):
            events.append({"type": "status", "node": "grounding",
                           "message": f"Grounding exception: {str(r)[:80]}"})
            continue
        name, text, msg = r
        site_scrapes[name] = text
        events.append({"type": "status", "node": "grounding", "message": msg})

    successful = sum(1 for v in site_scrapes.values() if v)
    events.append({
        "type":    "status",
        "node":    "grounding",
        "message": f"Grounding complete: {successful}/{len(all_companies)} companies scraped",
    })

    return {"site_scrapes": site_scrapes, "events": events}
