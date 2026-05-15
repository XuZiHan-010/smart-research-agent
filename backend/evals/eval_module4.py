"""Module 4: citation_resolver + editor/output prompt checks."""

import asyncio
import sys
from unittest.mock import AsyncMock, patch

from backend.nodes.citation_resolver import citation_resolver_node
from backend.nodes.output_formatter import output_formatter_node, _to_docx
from backend.prompts import EDITOR_MARKET_STUDY_PROMPT
from backend.services.citation_service import collect_citations, resolve_citations


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(("PASS" if ok else "FAIL"), name, detail)
    return ok


async def _run_resolver():
    state = {
        "job_id": "eval-module4",
        "report": "事实 [cite:doc_1]",
        "theme_reports": [{"citations": {"doc_1": {"title": "Source", "url": "https://example.com", "excerpt": "Excerpt"}}}],
    }
    with patch("backend.nodes.citation_resolver.db.update_job", new=AsyncMock()):
        return await citation_resolver_node(state)


async def _run_formatter():
    return await output_formatter_node({"output_format": "markdown", "report": "# 报告", "research_domain": "测试"})


def main() -> int:
    results = []
    citations = collect_citations([{"citations": {"a": {"url": "https://a.com"}}}])
    results.append(check("collect citations", "a" in citations))
    resolved, cmap = resolve_citations("A [cite:a]", {"a": {"title": "A", "url": "https://a.com", "excerpt": "E"}})
    results.append(check("resolve inline number", "[1]" in resolved and "关键来源清单" in resolved))
    resolver = asyncio.run(_run_resolver())
    results.append(check("citation resolver output", "[1]" in resolver["report"]))
    formatted = asyncio.run(_run_formatter())
    results.append(check("formatter markdown passthrough", formatted["output"] == "# 报告"))
    docx = _to_docx("# 标题\n\n正文")
    results.append(check("word bytes generated", isinstance(docx, bytes) and len(docx) > 1000))
    results.append(check("editor prompt exists", EDITOR_MARKET_STUDY_PROMPT is not None))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
