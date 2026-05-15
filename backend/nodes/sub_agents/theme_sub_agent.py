"""Theme sub-agent: isolated research context for one market-study theme."""

import asyncio
import json
import logging
import os
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from exa_py import Exa
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from backend.classes.config import (
    LLM_RATELIMIT_BACKOFF_BASE,
    LLM_RATELIMIT_MAX_RETRIES,
    SEMAPHORE_EXA_SEARCH,
    WRITER_DOCS_CHAR_BUDGET,
    WRITER_PER_DOC_EXCERPT_LIMIT,
)

logger = logging.getLogger(__name__)


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Detect OpenAI / generic 429 rate-limit errors across SDKs without
    importing the openai package (which the langchain_openai wrapper may
    re-raise under different class names). Matches only on strong markers
    so user-facing errors that incidentally mention 'rate limit' don't
    trigger backoff."""
    name = type(exc).__name__
    if "RateLimit" in name:
        return True
    msg = str(exc)
    return (
        "Error code: 429" in msg
        or "tokens per min" in msg
        or "Rate limit reached" in msg
        or "rate_limit_exceeded" in msg
    )


async def _retry_on_ratelimit(
    fn: Callable[[], Awaitable[Any]],
    *,
    label: str,
    max_retries: int = LLM_RATELIMIT_MAX_RETRIES,
    base_delay: float = LLM_RATELIMIT_BACKOFF_BASE,
) -> Any:
    """Run an async LLM call with exponential backoff on 429 rate-limit errors.
    Other exceptions propagate immediately."""
    last_exc: Optional[BaseException] = None
    for attempt in range(1, max_retries + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001 — we re-raise if not rate-limit
            if not _is_rate_limit_error(exc):
                raise
            last_exc = exc
            if attempt == max_retries:
                break
            # Honor server-provided retry hint if present (e.g. "Please try again in 23s").
            hint_match = re.search(r"try again in ([\d.]+)s", str(exc), re.IGNORECASE)
            if hint_match:
                delay = float(hint_match.group(1)) + 1.0
            else:
                delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "rate_limit_backoff label=%s attempt=%d/%d sleep=%.1fs err=%s",
                label, attempt, max_retries, delay, str(exc)[:200],
            )
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc
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
        self.writer_llm = ChatOpenAI(model="gpt-4.1", temperature=0.2, streaming=False)
        self.writer_model_name = "gpt-4.1"
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
            model=self.writer_model_name,
            prompt_name="THEME_REPORT_PROMPT",
            input_summary=f"{research_domain} / {self.theme_label_zh} / docs={len(documents)}",
            output_summary=str(report.get("narrative", ""))[:800],
            metadata={"theme_key": self.theme_key, "doc_count": len(documents), "retried": report.get("_retried", False)},
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
        payload = {
            "research_domain": research_domain,
            "theme_label_zh": self.theme_label_zh,
            "geography_labels": geography_labels,
            "time_start": time_range.get("start", ""),
            "time_end": time_range.get("end", ""),
            "authoritative_domains": ", ".join(AUTHORITATIVE_DOMAINS_BY_THEME.get(self.theme_key, [])),
            "format_guidelines": QUERY_FORMAT_GUIDELINES.format(num_queries=n_queries),
        }
        raw = await _retry_on_ratelimit(
            lambda: chain.ainvoke(payload),
            label=f"query_gen:{self.theme_key}",
        )
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

        docs_text, used_count = self._pack_documents_for_writer(documents)
        if used_count < len(documents):
            logger.info(
                "writer_docs_packed theme=%s used=%d/%d budget=%d chars",
                self.theme_key, used_count, len(documents), WRITER_DOCS_CHAR_BUDGET,
            )
        base_input = {
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
        }

        report = await self._invoke_writer(base_input, documents)

        # Quality gate: retry once with feedback if report has critical gaps.
        issues = self._assess_quality(report)
        if issues:
            feedback = (
                "[系统反馈：上次输出存在以下质量问题，请重新生成完整的 ThemeReport JSON，"
                "保留原有信息并修正这些问题，不要降级或简化：]\n- "
                + "\n- ".join(issues)
            )
            retry_input = dict(base_input)
            retry_input["documents"] = docs_text + "\n\n" + feedback
            retried = await self._invoke_writer(retry_input, documents)
            # Only adopt the retry if it actually improves quality; otherwise keep original.
            if len(self._assess_quality(retried)) < len(issues):
                retried["_retried"] = True
                report = retried
            else:
                report["_retried"] = False
                report.setdefault("data_gaps", [])
                report["data_gaps"] = list(report["data_gaps"]) + [
                    f"质量门控提示（重跑未改善）：{issue}" for issue in issues
                ]

        return report

    def _pack_documents_for_writer(
        self, documents: List[Dict[str, Any]]
    ) -> tuple[str, int]:
        """Pack documents into a single docs_text string bounded by
        WRITER_DOCS_CHAR_BUDGET. Iterates in given order (already score-sorted
        by _collect_documents), truncates each excerpt to
        WRITER_PER_DOC_EXCERPT_LIMIT, and stops adding once the global budget
        is exhausted. Returns (docs_text, count_used).

        This is the hard guard that keeps single LLM requests below the
        OpenAI gpt-4.1 TPM limit regardless of depth setting."""
        parts: List[str] = []
        remaining = WRITER_DOCS_CHAR_BUDGET
        used = 0
        separator_len = 2  # "\n\n"

        for doc in documents:
            raw_excerpt = (doc.get("excerpt") or "No excerpt")
            excerpt = raw_excerpt[:WRITER_PER_DOC_EXCERPT_LIMIT]
            block = (
                f"[{doc['doc_id']}] {doc.get('title')} ({doc.get('source')})\n"
                f"URL: {doc.get('url')}\n"
                f"Date: {doc.get('published_date') or 'unknown'}\n"
                f"Excerpt: {excerpt}"
            )
            cost = len(block) + (separator_len if parts else 0)
            if cost > remaining:
                # Try a smaller excerpt if even the metadata + tiny excerpt fits.
                shrunk_excerpt_budget = remaining - cost + len(excerpt) - 200
                if shrunk_excerpt_budget >= 300:
                    excerpt = excerpt[:shrunk_excerpt_budget]
                    block = (
                        f"[{doc['doc_id']}] {doc.get('title')} ({doc.get('source')})\n"
                        f"URL: {doc.get('url')}\n"
                        f"Date: {doc.get('published_date') or 'unknown'}\n"
                        f"Excerpt: {excerpt}"
                    )
                    cost = len(block) + (separator_len if parts else 0)
                    if cost <= remaining:
                        parts.append(block)
                        remaining -= cost
                        used += 1
                break
            parts.append(block)
            remaining -= cost
            used += 1

        return "\n\n".join(parts), used

    async def _invoke_writer(
        self, input_dict: Dict[str, Any], documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        chain = THEME_REPORT_PROMPT | self.writer_llm | StrOutputParser()
        raw = await _retry_on_ratelimit(
            lambda: chain.ainvoke(input_dict),
            label=f"writer:{self.theme_key}",
        )
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

    def _assess_quality(self, report: Dict[str, Any]) -> List[str]:
        """Return a list of quality issues. Empty list = pass."""
        issues: List[str] = []

        citations = report.get("citations") or {}
        if isinstance(citations, dict) and len(citations) < 5:
            issues.append(f"citations 仅 {len(citations)} 条，需 ≥ 5 个不同 doc_id")

        narrative = report.get("narrative") or ""
        if len(narrative) < 400:
            issues.append(f"narrative 长度 {len(narrative)} 字，需 ≥ 400 字")

        key_entities = report.get("key_entities") or {}
        if isinstance(key_entities, dict):
            non_empty = sum(1 for v in key_entities.values() if v)
            if non_empty < 2:
                issues.append(f"key_entities 仅 {non_empty} 类有内容，需 ≥ 2 类（公司/政策/事件/产品/数据等）")

        tables = report.get("tables") or []
        if not tables:
            issues.append("tables 为空，每个主题至少需要 1 个表格")
        else:
            # crude row-count proxy via pipe count: header + separator + ≥3 data rows = 5 lines ≈ 10 pipes
            longest = max(((t.get("markdown") or "").count("\n") for t in tables), default=0)
            if longest < 4:
                issues.append("tables 行数过少，每个表格至少需要 ≥ 3 数据行（不含表头与分隔行）")

        return issues

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
