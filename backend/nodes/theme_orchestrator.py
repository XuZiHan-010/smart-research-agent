"""Parallel theme orchestration node."""

import asyncio
from typing import Any, Dict, List, Tuple

from backend.classes.config import DEPTH_CONFIGS, SEMAPHORE_THEME_AGENTS
from backend.classes.market_study_config import THEME_LABELS_ZH
from backend.classes.state import ResearchState
from backend.nodes.sub_agents.theme_sub_agent import ThemeSubAgent
from backend.services import mongodb_service as db
from backend.services.trace_service import record_trace


def _theme_specs(selected_themes: List[str], custom_themes: List[str]) -> List[Tuple[str, str, bool]]:
    specs = [(key, THEME_LABELS_ZH.get(key, key), False) for key in selected_themes]
    specs.extend((f"custom_{idx + 1}", label, True) for idx, label in enumerate(custom_themes))
    return specs


async def theme_orchestrator_node(state: ResearchState) -> Dict[str, Any]:
    specs = _theme_specs(state.get("selected_themes", []), state.get("custom_themes", []))
    checkpoints = await db.get_checkpoints(state["job_id"])
    semaphore = asyncio.Semaphore(SEMAPHORE_THEME_AGENTS)
    events: List[Dict[str, Any]] = [{
        "type": "status",
        "node": "theme_orchestrator",
        "message": f"启动 {len(specs)} 个主题 sub-agent",
    }]

    async def run_one(theme_key: str, label: str, is_custom: bool) -> Dict[str, Any]:
        if theme_key in checkpoints:
            return checkpoints[theme_key]
        async with semaphore:
            depth_name = state.get("theme_depths", {}).get(theme_key, state.get("depth", "standard"))
            depth_cfg = DEPTH_CONFIGS.get(depth_name, DEPTH_CONFIGS["standard"])
            agent = ThemeSubAgent(
                job_id=state["job_id"],
                theme_key=theme_key,
                theme_label_zh=label,
                is_custom=is_custom,
            )
            return await agent.run(
                research_domain=state["research_domain"],
                geography=state["geography"],
                time_range=state["time_range"],
                queries_per_theme=depth_cfg["queries_per_theme"],
                results_per_query=depth_cfg["results_per_query"],
                max_docs_per_theme=depth_cfg["max_docs_per_theme"],
            )

    results = await asyncio.gather(
        *[run_one(theme_key, label, is_custom) for theme_key, label, is_custom in specs],
        return_exceptions=True,
    )
    theme_reports: List[Dict[str, Any]] = []
    todo_state: Dict[str, Dict[str, Any]] = {"themes": {}}
    for (theme_key, label, _), result in zip(specs, results):
        if isinstance(result, Exception):
            err_msg = f"{type(result).__name__}: {result}"
            await record_trace(
                state["job_id"],
                node="theme_sub_agent_error",
                model="n/a",
                prompt_name="theme_sub_agent",
                input_summary=f"theme={theme_key} label={label}",
                output_summary=err_msg[:1000],
                metadata={"theme_key": theme_key, "error_type": type(result).__name__},
            )
            report = {
                "theme_key": theme_key,
                "theme_label_zh": label,
                "is_custom": theme_key.startswith("custom_"),
                "narrative": "该主题研究失败，已记录为信息缺口。",
                "tables": [],
                "citations": {},
                "confidence": "low",
                "data_gaps": [err_msg[:500]],
            }
        else:
            report = result
        theme_reports.append(report)
        todo_state["themes"][theme_key] = {
            "status": "success" if report.get("citations") else "partial",
            "docs_found": len(report.get("citations") or {}),
            "label": label,
        }
        events.append({
            "type": "todo",
            "todo_state": todo_state,
            "dim_labels": {spec[0]: spec[1] for spec in specs},
        })

    await db.update_job(state["job_id"], {"theme_reports": theme_reports})
    events.append({
        "type": "status",
        "node": "theme_orchestrator",
        "message": "主题研究完成，进入跨主题校验",
    })
    return {"theme_reports": theme_reports, "events": events}
