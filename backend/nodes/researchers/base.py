"""
BaseResearcher — abstract base class for all 6 dimension researchers.

Key design decisions vs the original:
  1. Interface: run(company, site_scrape, queries_per_dim, results_per_query)
  2. Docs contain NO content field — fetched by Curator after filtering.
  3. Retry with exponential back-off.
  4. Standardised ResearchResult dict.
"""

import asyncio
import logging
import os
from abc import ABC
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv
from exa_py import Exa
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from backend.classes.config import (
    GROUNDING_QUERY_CHARS,
    MAX_RESEARCHER_RETRIES,
    RETRY_DELAY_BASE,
    SEMAPHORE_EXA_SEARCH,
)
from backend.query_prompts import QUERY_FORMAT_GUIDELINES

load_dotenv()

logger = logging.getLogger(__name__)

_RESTRICTED_CATEGORIES = {"company", "people"}
_exa_client: Optional[Exa] = None


def _get_exa() -> Exa:
    global _exa_client
    if _exa_client is None:
        _exa_client = Exa(api_key=os.getenv("EXA_API_KEY", "").strip())
    return _exa_client


def _months_ago(n: int) -> str:
    return (datetime.utcnow() - timedelta(days=30 * n)).strftime("%Y-%m-%d")


def _extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lstrip("www.")
    except Exception:
        return url


class BaseResearcher(ABC):
    DIMENSION: str = ""
    QUERY_PROMPT: ChatPromptTemplate = None
    EXA_SEARCH_CONFIGS: List[Dict[str, Any]] = [{"type": "neural"}]

    def __init__(self) -> None:
        self._query_llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0, streaming=False)
        self._search_semaphore = asyncio.Semaphore(SEMAPHORE_EXA_SEARCH)

    async def run(
        self,
        company: str,
        site_scrape: str,
        queries_per_dim: int,
        results_per_query: int,
    ) -> Dict[str, Any]:
        """Run full research cycle for one (company, dimension) pair."""
        result: Dict[str, Any] = {}
        for attempt in range(MAX_RESEARCHER_RETRIES + 1):
            result = await self._attempt(company, site_scrape, queries_per_dim, results_per_query)
            status = result["status"]
            if status in ("success", "partial", "empty"):
                return result
            if status == "error" and result.get("error_code") == "RATE_LIMIT":
                if attempt < MAX_RESEARCHER_RETRIES:
                    await asyncio.sleep(RETRY_DELAY_BASE * (attempt + 1))
                    continue
            return result
        return result

    async def _attempt(
        self,
        company: str,
        site_scrape: str,
        queries_per_dim: int,
        results_per_query: int,
    ) -> Dict[str, Any]:
        try:
            queries = await self._generate_queries(company, queries_per_dim, site_scrape)
        except Exception as e:
            return self._error_result(company, "EXCEPTION", str(e))

        all_docs: Dict[str, Dict] = {}
        try:
            for cfg_idx, cfg in enumerate(self.EXA_SEARCH_CONFIGS):
                override = cfg.get("queries_override")
                q_subset = queries[:override] if override else queries
                docs     = await self._search_parallel(q_subset, results_per_query, cfg)
                logger.info(
                    "%s %s cfg_idx=%d type=%s queries=%d docs=%d",
                    self.DIMENSION, company, cfg_idx,
                    cfg.get("type", "?"), len(q_subset), len(docs),
                )
                for url, doc in docs.items():
                    if url not in all_docs or doc["score"] > all_docs[url]["score"]:
                        all_docs[url] = doc
        except Exception as e:
            logger.warning(
                "%s _attempt raised company=%s: %s: %s",
                self.DIMENSION, company, type(e).__name__, e, exc_info=True,
            )
            err  = str(e).lower()
            code = "RATE_LIMIT" if ("rate" in err or "429" in err) else "API_TIMEOUT"
            return self._error_result(company, code, str(e))

        if not all_docs:
            return {
                "status": "empty", "company": company, "dimension": self.DIMENSION,
                "docs": [], "queries_run": len(queries),
                "docs_found": 0, "unique_domains": 0,
                "error_code": "NO_RESULTS", "error_message": None,
            }

        docs_list = list(all_docs.values())
        domains   = {_extract_domain(d["url"]) for d in docs_list}
        return {
            "status":         "success" if len(docs_list) >= 3 else "partial",
            "company":        company,
            "dimension":      self.DIMENSION,
            "docs":           docs_list,
            "queries_run":    len(queries),
            "docs_found":     len(docs_list),
            "unique_domains": len(domains),
            "error_code":     None,
            "error_message":  None,
        }

    async def _generate_queries(self, company: str, n_queries: int, site_scrape: str) -> List[str]:
        grounding_ctx = ""
        if site_scrape:
            grounding_ctx = f"\n\nOfficial website excerpt:\n{site_scrape[:GROUNDING_QUERY_CHARS]}"
        chain = self.QUERY_PROMPT | self._query_llm | StrOutputParser()
        raw: str = await chain.ainvoke({
            "company":           company,
            "num_queries":       n_queries,
            "format_guidelines": QUERY_FORMAT_GUIDELINES.format(num_queries=n_queries),
            "grounding_context": grounding_ctx,
        })
        return [q.strip() for q in raw.strip().splitlines() if q.strip()][:n_queries]

    async def _search_single(self, query: str, n_results: int, cfg: Dict[str, Any]) -> Dict[str, Dict]:
        exa      = _get_exa()
        category = cfg.get("category")
        kwargs: Dict[str, Any] = {
            "type": cfg.get("type", "neural"), "num_results": n_results,
        }
        if category:
            kwargs["category"] = category
        if category not in _RESTRICTED_CATEGORIES:
            if cfg.get("include_domains"):
                kwargs["include_domains"] = cfg["include_domains"]
            spd = cfg.get("start_published_date")
            if spd:
                kwargs["start_published_date"] = _months_ago(6) if spd == "dynamic" else spd
        elif cfg.get("include_domains") or cfg.get("start_published_date"):
            logger.warning(
                "%s: config has category=%s which silently disables "
                "include_domains/start_published_date — remove category or "
                "move filters to a separate config entry",
                self.DIMENSION, category,
            )

        loop = asyncio.get_event_loop()
        async with self._search_semaphore:
            try:
                response = await loop.run_in_executor(None, lambda: exa.search(query, **kwargs))
            except Exception as exc:
                logger.warning(
                    "%s exa.search raised query=%r kwargs=%s: %s: %s",
                    self.DIMENSION, query[:120], kwargs, type(exc).__name__, exc,
                )
                return {}

        docs: Dict[str, Dict] = {}
        try:
            for r in getattr(response, "results", None) or []:
                url = getattr(r, "url", None)
                if not url or url in docs:
                    continue
                try:
                    score = float(getattr(r, "score", 0.0) or 0.0)
                except (TypeError, ValueError):
                    score = 0.0
                docs[url] = {
                    "url":            url,
                    "title":          getattr(r, "title", "") or "",
                    "score":          score,
                    "published_date": getattr(r, "published_date", None),
                }
        except Exception as exc:
            logger.warning(
                "%s result parsing raised query=%r: %s: %s",
                self.DIMENSION, query[:120], type(exc).__name__, exc,
            )
        return docs

    async def _search_parallel(self, queries: List[str], n_results: int, cfg: Dict[str, Any]) -> Dict[str, Dict]:
        results = await asyncio.gather(
            *[self._search_single(q, n_results, cfg) for q in queries],
            return_exceptions=False,
        )
        merged: Dict[str, Dict] = {}
        for r in results:
            if not isinstance(r, dict):
                continue
            for url, doc in r.items():
                if url not in merged or doc["score"] > merged[url]["score"]:
                    merged[url] = doc
        return merged

    def _error_result(self, company: str, code: str, message: str) -> Dict[str, Any]:
        return {
            "status": "error", "company": company, "dimension": self.DIMENSION,
            "docs": [], "queries_run": 0, "docs_found": 0, "unique_domains": 0,
            "error_code": code, "error_message": message[:200],
        }
