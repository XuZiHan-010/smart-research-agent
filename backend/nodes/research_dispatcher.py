"""
Research Dispatcher node — fan-out across N companies × M dimensions.

Reads from state:
  all_companies      — [{name, website, source}]
  site_scrapes       — {company_name: crawled_text}
  active_dimensions  — subset of AVAILABLE_DIMENSIONS from router
  queries_per_dim    — int (from depth config)
  results_per_query  — int (from depth config)

Spawns one researcher task per (company, dimension) pair and runs them
concurrently under a global Semaphore(SEMAPHORE_RESEARCHERS).

Returns:
  research_results   — List[ResearchResultDict], appended via operator.add reducer
  events             — progress events (one per completed task)

Why dispatcher instead of putting this in graph.py fan-out edges:
  - N and M are dynamic (user controls number of competitors and report type)
  - LangGraph static fan-out requires knowing branch count at graph-build time
  - A single dispatcher node with asyncio.gather() handles arbitrary N×M cleanly
"""

import asyncio
from typing import Dict, Any, List

from backend.classes.state import CompetitorResearchState
from backend.classes.config import SEMAPHORE_RESEARCHERS
from backend.nodes.researchers import RESEARCHER_REGISTRY


async def research_dispatcher_node(state: CompetitorResearchState) -> Dict[str, Any]:
    all_companies:     List[Dict]  = state.get("all_companies", [])
    site_scrapes:      Dict        = state.get("site_scrapes", {})
    active_dimensions: List[str]   = state.get("active_dimensions", [])
    queries_per_dim:   int         = state.get("queries_per_dim", 4)
    results_per_query: int         = state.get("results_per_query", 5)

    # On evaluator retry, research only the failed dimensions (not the full matrix)
    retry_dimensions: List[str] = state.get("retry_dimensions", [])
    dims_to_run = retry_dimensions if retry_dimensions else active_dimensions
    is_retry    = bool(retry_dimensions)

    if not all_companies or not dims_to_run:
        return {
            "research_results": [],
            "events": [{"type": "status", "node": "research_dispatcher",
                        "message": "Nothing to research — skipping"}],
        }

    semaphore = asyncio.Semaphore(SEMAPHORE_RESEARCHERS)

    async def run_one(company: Dict[str, str], dimension: str) -> Dict[str, Any]:
        name        = company["name"]
        site_scrape = site_scrapes.get(name, "")

        researcher_cls = RESEARCHER_REGISTRY.get(dimension)
        if researcher_cls is None:
            return {
                "status": "error", "company": name, "dimension": dimension,
                "docs": [], "queries_run": 0, "docs_found": 0, "unique_domains": 0,
                "error_code": "UNKNOWN_DIMENSION", "error_message": f"No researcher for {dimension}",
            }

        async with semaphore:
            result = await researcher_cls().run(
                company=name,
                site_scrape=site_scrape,
                queries_per_dim=queries_per_dim,
                results_per_query=results_per_query,
            )
        return result

    # Build all (company, dimension) tasks — retry uses only failed dims
    tasks = [
        run_one(company, dim)
        for company in all_companies
        for dim in dims_to_run
    ]

    total = len(tasks)
    results: List[Dict] = []
    events:  List[Dict] = []

    events.append({
        "type":    "status",
        "node":    "research_dispatcher",
        "message": (
            f"{'[RETRY] ' if is_retry else ''}Starting {total} research tasks "
            f"({len(all_companies)} companies × {len(dims_to_run)} dimensions)"
        ),
    })

    # Run all tasks; gather exceptions so one failure doesn't abort everything
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    success = partial = empty = error = 0
    for r in raw_results:
        if isinstance(r, Exception):
            error += 1
            events.append({"type": "status", "node": "research_dispatcher",
                           "message": f"Task exception: {str(r)[:100]}"})
            continue

        results.append(r)
        status = r.get("status", "error")
        if   status == "success": success += 1
        elif status == "partial": partial += 1
        elif status == "empty":   empty   += 1
        else:                     error   += 1

        events.append({
            "type":      "status",
            "node":      "research_dispatcher",
            "company":   r.get("company"),
            "dimension": r.get("dimension"),
            "message": (
                f"{r.get('company')} / {r.get('dimension')}: "
                f"{status} — {r.get('docs_found', 0)} docs, "
                f"{r.get('unique_domains', 0)} domains"
            ),
        })

    events.append({
        "type":    "status",
        "node":    "research_dispatcher",
        "message": (
            f"Research complete — "
            f"{success} success, {partial} partial, {empty} empty, {error} errors "
            f"(total {total} tasks)"
        ),
    })

    return {"research_results": results, "events": events}
