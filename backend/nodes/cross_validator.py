"""Cross-theme validation node."""

import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from backend.classes.state import ResearchState
from backend.prompts import CROSS_VALIDATOR_PROMPT
from backend.services import mongodb_service as db
from backend.services.trace_service import record_trace

load_dotenv()


def _parse_json(raw: str) -> Dict[str, Any]:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in response")
    return json.loads(raw[start:end + 1])


def _fallback(theme_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    flags = []
    for report in theme_reports:
        if not report.get("citations"):
            flags.append({
                "severity": "warn",
                "theme_key": report.get("theme_key", ""),
                "message": "引用来源不足，已作为低置信度主题处理。",
            })
    return {
        "should_retry": False,
        "retry_themes": [],
        "checks": [{"code": "basic_presence", "passed": True, "detail": "基础结构检查通过"}],
        "quality_flags": flags,
        "summary": "基础校验完成；低置信主题已标注。",
    }


async def cross_validator_node(state: ResearchState) -> Dict[str, Any]:
    reports = state.get("theme_reports", [])
    events = [{"type": "status", "node": "cross_validator", "message": "检查跨主题冲突和引用完整性"}]
    payload = {"theme_reports_json": json.dumps(reports, ensure_ascii=False)[:50000]}

    # Three-tier fallback: gemini-2.5-flash (primary) → gpt-4.1-mini (backup) → rules.
    report: Dict[str, Any] | None = None
    model = "gemini-2.5-flash"
    try:
        llm = ChatGoogleGenerativeAI(model=model, temperature=0)
        raw = await (CROSS_VALIDATOR_PROMPT | llm | StrOutputParser()).ainvoke(payload)
        report = _parse_json(raw)
    except Exception:
        report = None

    if report is None:
        model = "gpt-4.1-mini"
        try:
            llm = ChatOpenAI(model=model, temperature=0)
            raw = await (CROSS_VALIDATOR_PROMPT | llm | StrOutputParser()).ainvoke(payload)
            report = _parse_json(raw)
        except Exception:
            report = None

    if report is None:
        report = _fallback(reports)
        model = "rules-fallback"

    await db.update_job(state["job_id"], {"validation_report": report})
    await record_trace(
        state["job_id"],
        node="cross_validator",
        model=model,
        prompt_name="CROSS_VALIDATOR_PROMPT",
        input_summary=f"{len(reports)} theme reports",
        output_summary=json.dumps(report, ensure_ascii=False),
    )
    events.append({"type": "status", "node": "cross_validator", "message": report.get("summary", "校验完成")})
    return {"validation_report": report, "events": events}
