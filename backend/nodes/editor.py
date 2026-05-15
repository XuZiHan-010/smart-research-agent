"""Chinese market-study editor node."""

import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from backend.classes.market_study_config import GEOGRAPHY_LABELS_ZH
from backend.classes.state import ResearchState
from backend.prompts import EDITOR_MARKET_STUDY_PROMPT
from backend.services import mongodb_service as db
from backend.services.trace_service import record_trace

load_dotenv()


def _section_order_text(sections: List[Dict[str, Any]]) -> str:
    lines = []
    for idx, section in enumerate(sections, start=1):
        lines.append(f"{idx}. {section.get('label_zh')}")
    return "\n".join(lines)


async def editor_node(state: ResearchState) -> Dict[str, Any]:
    skeleton = state.get("compacted_skeleton", {}) or {}
    sections = skeleton.get("sections", [])
    geography_labels = "、".join(GEOGRAPHY_LABELS_ZH.get(g, g) for g in state.get("geography", []))
    validation = state.get("validation_report", {}) or {}
    events: List[Dict[str, Any]] = [{
        "type": "status",
        "node": "editor",
        "message": "开始生成中文市场调研报告",
    }]

    llm = ChatOpenAI(
        model="gpt-4.1",
        temperature=0.25,
        streaming=True,
        api_key=os.getenv("OPENAI_API_KEY", ""),
    )
    chain = EDITOR_MARKET_STUDY_PROMPT | llm | StrOutputParser()
    full_report = ""
    invoke_vars = {
        "research_domain": state["research_domain"],
        "geography_labels": geography_labels,
        "time_start": state["time_range"].get("start", ""),
        "time_end": state["time_range"].get("end", ""),
        "today": state["time_range"].get("today", ""),
        "section_order": _section_order_text(sections),
        "validation_summary": validation.get("summary", ""),
        "skeleton": json.dumps(skeleton, ensure_ascii=False),
    }
    async for chunk in chain.astream(invoke_vars):
        full_report += chunk
        events.append({"type": "stream", "node": "editor", "content": chunk})

    await db.update_job(state["job_id"], {"report": full_report})
    await record_trace(
        state["job_id"],
        node="editor",
        model="gpt-4.1",
        prompt_name="EDITOR_MARKET_STUDY_PROMPT",
        input_summary=f"{state['research_domain']} / {len(sections)} sections",
        output_summary=full_report[:1000],
    )
    events.append({"type": "status", "node": "editor", "message": f"报告初稿生成完成（{len(full_report)} 字符）"})
    return {"report": full_report, "events": events}
