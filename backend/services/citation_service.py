"""Citation helpers for converting [cite:doc_id] markers to numbered links."""

import re
from typing import Any, Dict, Iterable, Tuple

_CITE_RE = re.compile(r"\[cite:([A-Za-z0-9_\-:.]+)\]")


def collect_citations(theme_reports: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    citations: Dict[str, Dict[str, Any]] = {}
    for report in theme_reports:
        for doc_id, citation in (report.get("citations") or {}).items():
            citations.setdefault(doc_id, citation)
    return citations


def resolve_citations(markdown: str, citations: Dict[str, Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    ordered: Dict[str, int] = {}

    def repl(match: re.Match[str]) -> str:
        doc_id = match.group(1)
        if doc_id not in ordered:
            ordered[doc_id] = len(ordered) + 1
        return f"[{ordered[doc_id]}]"

    resolved = _CITE_RE.sub(repl, markdown)

    lines = ["", "## 关键来源清单", "", "| 编号 | 来源 | 链接 | 摘要 |", "|---|---|---|---|"]
    for doc_id, idx in sorted(ordered.items(), key=lambda item: item[1]):
        citation = citations.get(doc_id, {})
        title = str(citation.get("title") or citation.get("source") or doc_id).replace("|", " ")
        url = str(citation.get("url") or "").strip()
        excerpt = str(citation.get("excerpt") or "").replace("\n", " ").replace("|", " ")[:180]
        source = f"[{title}]({url})" if url else title
        link_cell = url if url else "—"
        lines.append(f"| [{idx}] | {source} | {link_cell} | {excerpt} |")

    if ordered and "## 关键来源清单" not in resolved:
        resolved = resolved.rstrip() + "\n" + "\n".join(lines)
    return resolved, {"ordered_doc_ids": ordered, "citations": citations}
