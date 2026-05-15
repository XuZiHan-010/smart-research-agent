"""LLM trace recording facade."""

from typing import Any, Dict, List

from backend.services import mongodb_service as db


async def record_trace(
    job_id: str,
    *,
    node: str,
    model: str,
    prompt_name: str,
    input_summary: str,
    output_summary: str = "",
    metadata: Dict[str, Any] | None = None,
) -> None:
    await db.record_trace(job_id, {
        "node": node,
        "model": model,
        "prompt_name": prompt_name,
        "input_summary": input_summary[:1000],
        "output_summary": output_summary[:1000],
        "metadata": metadata or {},
    })


async def list_traces(job_id: str) -> List[Dict[str, Any]]:
    return await db.get_traces(job_id)
