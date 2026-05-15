"""Compact ThemeReports into an editor-friendly skeleton."""

from typing import Any, Dict, List

from backend.classes.market_study_config import THEME_LABELS_ZH
from backend.classes.state import ResearchState
from backend.services import mongodb_service as db


def _section_order(selected_themes: List[str], custom_themes: List[str]) -> List[Dict[str, Any]]:
    order = []
    for key in selected_themes:
        order.append({"theme_key": key, "label_zh": THEME_LABELS_ZH.get(key, key), "is_custom": False})
    for idx, label in enumerate(custom_themes):
        order.append({"theme_key": f"custom_{idx + 1}", "label_zh": label, "is_custom": True})
    return order


async def compactor_node(state: ResearchState) -> Dict[str, Any]:
    reports_by_key = {r.get("theme_key"): r for r in state.get("theme_reports", [])}
    sections = []
    for item in _section_order(state.get("selected_themes", []), state.get("custom_themes", [])):
        report = reports_by_key.get(item["theme_key"], {})
        sections.append({
            **item,
            "narrative": str(report.get("narrative", ""))[:12000],
            "tables": report.get("tables", [])[:5],
            "confidence": report.get("confidence", "low"),
            "data_gaps": report.get("data_gaps", []),
            "forecast_section": report.get("forecast_section"),
            "key_entities": report.get("key_entities") or {},
        })
    skeleton = {"sections": sections}
    await db.update_job(state["job_id"], {"compacted_skeleton": skeleton})
    return {
        "compacted_skeleton": skeleton,
        "events": [{"type": "status", "node": "compactor", "message": "已压缩主题报告，准备生成中文报告"}],
    }
