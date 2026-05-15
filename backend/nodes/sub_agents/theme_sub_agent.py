"""Theme sub-agent: isolated research context for one market-study theme."""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from exa_py import Exa
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from backend.classes.config import SEMAPHORE_EXA_SEARCH
from backend.classes.market_study_config import (
    AUTHORITATIVE_DOMAINS_BY_THEME,
    GEOGRAPHY_LABELS_ZH,
    THEME_TABLE_SCHEMAS,
)
from backend.prompts import THEME_REPORT_PROMPT
from backend.query_prompts import QUERY_FORMAT_GUIDELINES, THEME_QUERY_PROMPT
from backend.services import mongodb_service as db
from backend.services.trace_service import record_trace

load_dotenv()

_exa_client: Optional[Exa] = None


def _get_exa() -> Exa:
    global _exa_client
    if _exa_client is None:
        _exa_client = Exa(api_key=os.getenv("EXA_API_KEY", "").strip())
    return _exa_client


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lstrip("www.")
    except Exception:
        return url


def _json_loads(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start:end + 1]
    return json.loads(cleaned)


class ThemeSubAgent:
    def __init__(self, *, job_id: str, theme_key: str, theme_label_zh: str, is_custom: bool) -> None:
        self.job_id = job_id
        self.theme_key = theme_key
        self.theme_label_zh = theme_label_zh
        self.is_custom = is_custom
        self.query_llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0, streaming=False)
        self.writer_llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.2, streaming=False)
        self.search_semaphore = asyncio.Semaphore(SEMAPHORE_EXA_SEARCH)

    async def run(
        self,
        *,
        research_domain: str,
        geography: List[str],
        time_range: Dict[str, str],
        queries_per_theme: int,
        results_per_query: int,
        max_docs_per_theme: int,
    ) -> Dict[str, Any]:
        geography_labels = "、".join(GEOGRAPHY_LABELS_ZH.get(g, g) for g in geography)
        documents = await self._collect_documents(
            research_domain=research_domain,
            geography_labels=geography_labels,
            time_range=time_range,
            queries_per_theme=queries_per_theme,
            results_per_query=results_per_query,
            max_docs_per_theme=max_docs_per_theme,
        )
        report = await self._write_report(
            research_domain=research_domain,
            geography_labels=geography_labels,
            time_range=time_range,
            documents=documents,
        )
        await db.save_checkpoint(self.job_id, self.theme_key, report)
        await record_trace(
            self.job_id,
            node="theme_sub_agent",
            model="gpt-4.1-mini",
            prompt_name="THEME_REPORT_PROMPT",
            input_summary=f"{research_domain} / {self.theme_label_zh} / docs={len(documents)}",
            output_summary=str(report.get("narrative", ""))[:800],
            metadata={"theme_key": self.theme_key, "doc_count": len(documents)},
        )
        return report

    async def _collect_documents(
        self,
        *,
        research_domain: str,
        geography_labels: str,
        time_range: Dict[str, str],
        queries_per_theme: int,
        results_per_query: int,
        max_docs_per_theme: int,
    ) -> List[Dict[str, Any]]:
        queries = await self._generate_queries(
            research_domain, geography_labels, time_range, queries_per_theme
        )
        results = await asyncio.gather(
            *[self._search_one(query, results_per_query) for query in queries],
            return_exceptions=True,
        )
        by_url: Dict[str, Dict[str, Any]] = {}
        for result in results:
            if not isinstance(result, list):
                continue
            for doc in result:
                url = doc.get("url")
                if not url:
                    continue
                if url not in by_url or doc.get("score", 0) > by_url[url].get("score", 0):
                    by_url[url] = doc
        docs = sorted(by_url.values(), key=lambda d: d.get("score", 0), reverse=True)[:max_docs_per_theme]
        for idx, doc in enumerate(docs, start=1):
            doc["doc_id"] = f"{self.theme_key}_{idx}"
        return docs

    async def _generate_queries(
        self,
        research_domain: str,
        geography_labels: str,
        time_range: Dict[str, str],
        n_queries: int,
    ) -> List[str]:
        chain = THEME_QUERY_PROMPT | self.query_llm | StrOutputParser()
        raw = await chain.ainvoke({
            "research_domain": research_domain,
            "theme_label_zh": self.theme_label_zh,
            "geography_labels": geography_labels,
            "time_start": time_range.get("start", ""),
            "time_end": time_range.get("end", ""),
            "authoritative_domains": ", ".join(AUTHORITATIVE_DOMAINS_BY_THEME.get(self.theme_key, [])),
            "format_guidelines": QUERY_FORMAT_GUIDELINES.format(num_queries=n_queries),
        })
        await record_trace(
            self.job_id,
            node="query_generator",
            model="gpt-4.1-mini",
            prompt_name="THEME_QUERY_PROMPT",
            input_summary=f"{research_domain} / {self.theme_label_zh}",
            output_summary=raw,
            metadata={"theme_key": self.theme_key},
        )
        queries = [line.strip("-• \t") for line in raw.splitlines() if line.strip()]
        return queries[:n_queries] or [f"{research_domain} {self.theme_label_zh} 市场 报告"]

    async def _search_one(self, query: str, n_results: int) -> List[Dict[str, Any]]:
        exa = _get_exa()
        loop = asyncio.get_running_loop()
        async with self.search_semaphore:
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda: exa.search_and_contents(
                        query,
                        type="neural",
                        num_results=n_results,
                        text={"max_characters": 6000},
                    ),
                )
            except Exception:
                response = await loop.run_in_executor(
                    None,
                    lambda: exa.search(query, type="neural", num_results=n_results),
                )
        docs: List[Dict[str, Any]] = []
        for item in getattr(response, "results", None) or []:
            url = getattr(item, "url", "") or ""
            text = getattr(item, "text", "") or getattr(item, "highlights", "") or ""
            if isinstance(text, list):
                text = " ".join(str(t) for t in text)
            docs.append({
                "url": url,
                "title": getattr(item, "title", "") or _domain(url),
                "source": _domain(url),
                "score": float(getattr(item, "score", 0.0) or 0.0),
                "published_date": getattr(item, "published_date", None),
                "excerpt": str(text)[:6000],
            })
        return docs

    async def _write_report(
        self,
        *,
        research_domain: str,
        geography_labels: str,
        time_range: Dict[str, str],
        documents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not documents:
            return self._empty_report()

        docs_text = "\n\n".join(
            f"[{doc['doc_id']}] {doc.get('title')} ({doc.get('source')})\n"
            f"URL: {doc.get('url')}\n"
            f"Date: {doc.get('published_date') or 'unknown'}\n"
            f"Excerpt: {doc.get('excerpt') or 'No excerpt'}"
            for doc in documents
        )
        chain = THEME_REPORT_PROMPT | self.writer_llm | StrOutputParser()
        raw = await chain.ainvoke({
            "research_domain": research_domain,
            "theme_key": self.theme_key,
            "theme_label_zh": self.theme_label_zh,
            "is_custom": str(self.is_custom),
            "geography_labels": geography_labels,
            "time_start": time_range.get("start", ""),
            "time_end": time_range.get("end", ""),
            "today": time_range.get("today", ""),
            "table_schema": "自定义主题：如适用请自行设计表格" if self.is_custom else THEME_TABLE_SCHEMAS.get(self.theme_key, ""),
            "documents": docs_text,
        })
        try:
            report = _json_loads(raw)
        except Exception:
            report = self._fallback_report(documents, raw)
        report["theme_key"] = self.theme_key
        report["theme_label_zh"] = self.theme_label_zh
        report["is_custom"] = self.is_custom
        report.setdefault("citations", {
            doc["doc_id"]: {
                "doc_id": doc["doc_id"],
                "title": doc.get("title", ""),
                "url": doc.get("url", ""),
                "source": doc.get("source", ""),
                "published_date": doc.get("published_date"),
                "excerpt": doc.get("excerpt", "")[:240],
            }
            for doc in documents
        })
        return report

    def _empty_report(self) -> Dict[str, Any]:
        return {
            "theme_key": self.theme_key,
            "theme_label_zh": self.theme_label_zh,
            "is_custom": self.is_custom,
            "narrative": "公开资料不足，无法形成可靠结论。",
            "tables": [{"title": "资料缺口", "markdown": "| 缺口 | 说明 |\n|---|---|\n| 公开资料 | 未检索到足够来源 |", "notes": ""}],
            "citations": {},
            "confidence": "low",
            "data_gaps": ["未检索到足够公开资料。"],
            "forecast_section": None,
        }

    def _fallback_report(self, documents: List[Dict[str, Any]], raw: str) -> Dict[str, Any]:
        citations = {
            doc["doc_id"]: {
                "doc_id": doc["doc_id"],
                "title": doc.get("title", ""),
                "url": doc.get("url", ""),
                "source": doc.get("source", ""),
                "published_date": doc.get("published_date"),
                "excerpt": doc.get("excerpt", "")[:240],
            }
            for doc in documents
        }
        first = documents[0]["doc_id"] if documents else ""
        return {
            "theme_key": self.theme_key,
            "theme_label_zh": self.theme_label_zh,
            "is_custom": self.is_custom,
            "narrative": f"{raw[:1800]} {'[cite:' + first + ']' if first else ''}",
            "tables": [{"title": "核心来源", "markdown": "| 来源 | 主题相关性 |\n|---|---|\n" + "\n".join(f"| {d.get('title','')} | {self.theme_label_zh} |" for d in documents[:5]), "notes": ""}],
            "citations": citations,
            "confidence": "medium" if len(documents) >= 3 else "low",
            "data_gaps": [],
            "forecast_section": None,
        }
