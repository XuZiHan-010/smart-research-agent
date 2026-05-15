"""Module 2: theme_sub_agent + theme_orchestrator checks."""

import asyncio
import sys
from unittest.mock import AsyncMock, patch

from backend.nodes.theme_orchestrator import _theme_specs, theme_orchestrator_node
from backend.nodes.sub_agents.theme_sub_agent import ThemeSubAgent, _json_loads


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(("PASS" if ok else "FAIL"), name, detail)
    return ok


async def _run_orchestrator_mocked():
    async def fake_run(self, **_kwargs):
        return {
            "theme_key": self.theme_key,
            "theme_label_zh": self.theme_label_zh,
            "is_custom": self.is_custom,
            "narrative": "ok",
            "tables": [],
            "citations": {"doc": {"url": "https://example.com"}},
            "confidence": "high",
            "data_gaps": [],
        }

    state = {
        "job_id": "eval-module2",
        "research_domain": "中国动力电池市场",
        "selected_themes": ["market_size", "policy"],
        "custom_themes": ["ESG"],
        "geography": ["cn"],
        "time_range": {"start": "2021-01", "end": "2031-01", "today": "2026-05"},
        "depth": "snapshot",
    }
    with patch("backend.nodes.theme_orchestrator.db.get_checkpoints", new=AsyncMock(return_value={})), \
         patch("backend.nodes.theme_orchestrator.db.update_job", new=AsyncMock()), \
         patch.object(ThemeSubAgent, "run", new=fake_run):
        return await theme_orchestrator_node(state)


def main() -> int:
    results = []
    specs = _theme_specs(["market_size"], ["ESG", "出海"])
    results.append(check("theme specs include custom order", [s[0] for s in specs] == ["market_size", "custom_1", "custom_2"]))
    results.append(check("json parser strips fences", _json_loads("```json\n{\"a\":1}\n```") == {"a": 1}))
    output = asyncio.run(_run_orchestrator_mocked())
    reports = output["theme_reports"]
    results.append(check("orchestrator returns 3 reports", len(reports) == 3))
    results.append(check("todo event emitted", any(e.get("type") == "todo" for e in output["events"])))
    results.append(check("custom report marked", any(r["is_custom"] for r in reports)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
