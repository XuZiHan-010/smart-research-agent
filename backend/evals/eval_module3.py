"""Module 3: cross_validator + compactor checks."""

import asyncio
import sys
from unittest.mock import AsyncMock, patch

from backend.nodes.compactor import _section_order, compactor_node
from backend.nodes.cross_validator import _fallback, cross_validator_node


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(("PASS" if ok else "FAIL"), name, detail)
    return ok


async def _run_compactor():
    state = {
        "job_id": "eval-module3",
        "selected_themes": ["market_size", "policy"],
        "custom_themes": ["ESG"],
        "theme_reports": [
            {"theme_key": "market_size", "narrative": "A" * 8000, "tables": [{"title": "T"}], "citations": {}, "confidence": "high"},
            {"theme_key": "policy", "narrative": "policy", "tables": [], "citations": {}, "confidence": "medium"},
            {"theme_key": "custom_1", "narrative": "custom", "tables": [], "citations": {}, "confidence": "low"},
        ],
    }
    with patch("backend.nodes.compactor.db.update_job", new=AsyncMock()):
        return await compactor_node(state)


async def _run_validator():
    state = {"job_id": "eval-module3", "theme_reports": [{"theme_key": "x", "citations": {}}]}
    with patch("backend.nodes.cross_validator.db.update_job", new=AsyncMock()), \
         patch("backend.nodes.cross_validator.record_trace", new=AsyncMock()):
        return await cross_validator_node(state)


def main() -> int:
    results = []
    order = _section_order(["market_size"], ["ESG"])
    results.append(check("section order fixed then custom", [o["theme_key"] for o in order] == ["market_size", "custom_1"]))
    fallback = _fallback([{"theme_key": "x", "citations": {}}])
    results.append(check("fallback flags missing citations", bool(fallback["quality_flags"])))
    compacted = asyncio.run(_run_compactor())["compacted_skeleton"]
    results.append(check("compactor keeps 3 sections", len(compacted["sections"]) == 3))
    results.append(check("compactor truncates narrative", len(compacted["sections"][0]["narrative"]) == 6000))
    validator = asyncio.run(_run_validator())
    results.append(check("validator returns validation_report", "validation_report" in validator))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
