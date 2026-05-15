"""FastAPI server for the Market Study Agent."""

import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.classes.config import VALID_DEPTHS
from backend.classes.market_study_config import THEME_LABELS_ZH
from backend.classes.state import job_status
from backend.graph import Graph
from backend.services import mongodb_service as db
from backend.services.clarification_service import build_questionnaire
from backend.services.trace_service import list_traces

load_dotenv()

app = FastAPI(title="Market Study Agent API", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"(https?://)?(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.up\.railway\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    try:
        await db.ensure_indexes()
    except Exception:
        pass


def _get_caller_email(request: Request) -> str:
    return request.headers.get("Cf-Access-Authenticated-User-Email", "anonymous")


class ClarifyRequest(BaseModel):
    confirmed_domain: str


class ConfirmRequest(BaseModel):
    clarification_id: str
    selected_themes: List[str] = Field(default_factory=list)
    custom_themes: List[str] = Field(default_factory=list)
    geography: List[str] = Field(default_factory=list)
    time_range: Dict[str, str]
    depth: str = "standard"
    theme_depths: Dict[str, str] = Field(default_factory=dict)


async def _run_pipeline(job_id: str, graph: Graph) -> None:
    job_status[job_id]["status"] = "processing"
    try:
        async for event in graph.run():
            job_status[job_id]["events"].append(event)
        final = graph.get_final_state()
        report = final.get("report", "")
        job_status[job_id].update({
            "status": "completed",
            "report": report,
            "output": final.get("output"),
            "last_update": datetime.now().isoformat(),
        })
        await db.complete_job(job_id, report, {
            "output": final.get("output") if isinstance(final.get("output"), str) else None,
            "citations_map": final.get("citations_map", {}),
        })
    except Exception as exc:
        error = str(exc)
        job_status[job_id].update({
            "status": "failed",
            "error": error,
            "last_update": datetime.now().isoformat(),
        })
        await db.fail_job(job_id, error)


def _validate_confirm(req: ConfirmRequest) -> None:
    if req.depth not in VALID_DEPTHS:
        raise HTTPException(400, f"Invalid depth: {req.depth}. Valid: {VALID_DEPTHS}")
    invalid_depths = {key: value for key, value in req.theme_depths.items() if value not in VALID_DEPTHS}
    if invalid_depths:
        raise HTTPException(400, f"Invalid theme_depths: {invalid_depths}. Valid: {VALID_DEPTHS}")
    valid_themes = set(THEME_LABELS_ZH)
    unknown = [theme for theme in req.selected_themes if theme not in valid_themes]
    if unknown:
        raise HTTPException(400, f"Unknown selected_themes: {unknown}")
    custom = [theme.strip() for theme in req.custom_themes if theme.strip()]
    if len(custom) > 3:
        raise HTTPException(400, "custom_themes supports at most 3 items")
    if not req.selected_themes and not custom:
        raise HTTPException(400, "Select at least one default or custom theme")
    if not req.geography:
        raise HTTPException(400, "Select at least one geography")
    start = req.time_range.get("start")
    end = req.time_range.get("end")
    today = req.time_range.get("today")
    if not start or not end or start >= end:
        raise HTTPException(400, "time_range.start must be before time_range.end")
    if not today:
        raise HTTPException(400, "time_range.today is required (format: YYYY-MM)")
    labels = set(THEME_LABELS_ZH.values())
    dup = [theme for theme in custom if theme in labels]
    if dup:
        raise HTTPException(400, f"Custom theme duplicates default theme label: {dup}")


@app.post("/api/research/clarify")
async def clarify(req: ClarifyRequest):
    if not req.confirmed_domain.strip():
        raise HTTPException(400, "confirmed_domain is required")
    try:
        return await build_questionnaire(req.confirmed_domain)
    except Exception as exc:
        raise HTTPException(503, detail=f"Database unavailable — cannot create questionnaire: {exc}")


@app.post("/api/research/confirm")
async def confirm(req: ConfirmRequest, background_tasks: BackgroundTasks, request: Request):
    _validate_confirm(req)
    clarification = await db.get_clarification(req.clarification_id)
    if not clarification:
        raise HTTPException(404, "Clarification not found or expired")

    research_domain = clarification.get("research_domain", "")
    job_id = str(uuid.uuid4())
    try:
        await db.cleanup_oldest(keep=20)
    except Exception:
        pass
    try:
        await db.create_job(job_id, {
            "research_domain": research_domain,
            "selected_themes": req.selected_themes,
            "custom_themes": [theme.strip() for theme in req.custom_themes if theme.strip()],
            "geography": req.geography,
            "time_range": req.time_range,
            "depth": req.depth,
            "theme_depths": req.theme_depths,
            "output_format": "markdown",
            "created_by": _get_caller_email(request),
        })
    except Exception as exc:
        raise HTTPException(503, detail=f"Database unavailable — cannot start job: {exc}")

    job_status[job_id]["status"] = "pending"
    job_status[job_id]["research_domain"] = research_domain
    job_status[job_id]["output_format"] = "markdown"
    job_status[job_id]["events"] = []

    graph = Graph(
        research_domain=research_domain,
        selected_themes=req.selected_themes,
        custom_themes=[theme.strip() for theme in req.custom_themes if theme.strip()],
        geography=req.geography,
        time_range=req.time_range,
        depth=req.depth,
        theme_depths=req.theme_depths,
        output_format="markdown",
        job_id=job_id,
    )
    background_tasks.add_task(_run_pipeline, job_id, graph)
    return {"job_id": job_id, "research_domain": research_domain, "depth": req.depth}


@app.get("/api/research/{job_id}/stream")
async def stream_research(job_id: str):
    if job_id not in job_status:
        job = await db.get_job(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        if job.get("status") == "completed":
            async def _replay():
                payload = json.dumps({"type": "complete", "job_id": job_id, "report": job.get("report", "")}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            return StreamingResponse(_replay(), media_type="text/event-stream")
        raise HTTPException(404, "Job not found in active session")

    async def _generator():
        for _ in range(50):
            if job_status[job_id]["status"] != "pending":
                break
            await asyncio.sleep(0.1)
        while True:
            status = job_status[job_id]["status"]
            events = job_status[job_id]["events"]
            while events:
                yield f"data: {json.dumps(events.pop(0), ensure_ascii=False)}\n\n"
            if status == "completed":
                payload = json.dumps({
                    "type": "complete",
                    "job_id": job_id,
                    "report": job_status[job_id].get("report", ""),
                }, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                break
            if status == "failed":
                payload = json.dumps({
                    "type": "error",
                    "job_id": job_id,
                    "message": job_status[job_id].get("error", "Unknown error"),
                }, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                break
            await asyncio.sleep(0.15)

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/research/{job_id}/report")
async def get_report(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        mem = job_status.get(job_id)
        if not mem:
            raise HTTPException(404, "Job not found")
        if mem.get("status") == "completed":
            return {"status": "completed", "job_id": job_id, "report": mem.get("report", "")}
        if mem.get("status") == "failed":
            raise HTTPException(500, mem.get("error", "Unknown error"))
        return JSONResponse(status_code=202, content={"status": mem.get("status"), "message": "Still processing"})

    status = job.get("status", "unknown")
    if status == "completed":
        return {
            "status": "completed",
            "job_id": job_id,
            "research_domain": job.get("research_domain"),
            "depth": job.get("depth"),
            "output_format": job.get("output_format"),
            "report": job.get("report", ""),
            "report_version": job.get("report_version", 1),
            "created_at": job.get("created_at"),
            "completed_at": job.get("completed_at"),
        }
    if status == "failed":
        raise HTTPException(500, job.get("error", "Unknown error"))
    return JSONResponse(status_code=202, content={"status": status, "message": "Still processing"})


@app.get("/api/research/{job_id}/download")
async def download_report(job_id: str, format: str = Query("markdown", description="markdown | pdf | word")):
    job = await db.get_job(job_id)
    if not job or not job.get("report"):
        raise HTTPException(404, "Report not found")
    report = job["report"]

    if format == "pdf":
        import tempfile
        from backend.services.pdf_service import PDFService
        from fastapi.responses import FileResponse

        domain = job.get("research_domain", "market-study")
        ok, result = PDFService().generate_pdf_bytes(report, domain, language="zh")
        if not ok:
            raise HTTPException(500, f"PDF generation failed: {result}")

        # Write to temp file and return as FileResponse
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            temp_path = f.name
            f.write(result)

        return FileResponse(
            path=temp_path,
            media_type="application/pdf",
            filename="report.pdf",
        )
    if format == "word":
        import tempfile
        from backend.nodes.output_formatter import _to_docx
        from fastapi.responses import FileResponse

        docx_bytes = _to_docx(report)

        # Write to temp file and return as FileResponse
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            temp_path = f.name
            f.write(docx_bytes)

        return FileResponse(
            path=temp_path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="report.docx",
        )
    if format == "md":
        format = "markdown"
    if format != "markdown":
        raise HTTPException(400, "format must be markdown, md, pdf, or word")

    import tempfile
    from fastapi.responses import FileResponse

    # Write to temp file and return as FileResponse
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
        temp_path = f.name
        f.write(report)

    return FileResponse(
        path=temp_path,
        media_type="text/markdown; charset=utf-8",
        filename="report.md",
    )


@app.get("/api/research/{job_id}/traces")
async def traces(job_id: str):
    return {"job_id": job_id, "traces": await list_traces(job_id)}


@app.post("/api/research/{job_id}/resume")
async def resume(job_id: str, background_tasks: BackgroundTasks):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job_status[job_id]["status"] = "pending"
    job_status[job_id]["research_domain"] = job.get("research_domain")
    job_status[job_id]["output_format"] = "markdown"
    job_status[job_id]["events"] = []
    graph = Graph(
        research_domain=job.get("research_domain", ""),
        selected_themes=job.get("selected_themes", []),
        custom_themes=job.get("custom_themes", []),
        geography=job.get("geography", []),
        time_range=job.get("time_range", {}),
        depth=job.get("depth", "standard"),
        theme_depths=job.get("theme_depths", {}),
        output_format="markdown",
        job_id=job_id,
    )
    await db.update_job(job_id, {"status": "running", "error": None})
    background_tasks.add_task(_run_pipeline, job_id, graph)
    return {"job_id": job_id, "status": "processing"}


@app.get("/api/research/history")
async def get_history(limit: int = Query(50, ge=1, le=200)):
    try:
        jobs = await db.get_history(limit)
    except Exception:
        return {"jobs": [], "count": 0, "error": "Database unavailable"}
    return {"jobs": jobs, "count": len(jobs)}


@app.delete("/api/research/{job_id}")
async def delete_job(job_id: str):
    deleted = await db.delete_job(job_id)
    job_status.pop(job_id, None)
    if not deleted:
        raise HTTPException(404, "Job not found")
    return {"deleted": True, "job_id": job_id}


class CleanupRequest(BaseModel):
    keep: int = Field(10, ge=1, le=100)


@app.post("/api/research/cleanup")
async def cleanup_storage(req: CleanupRequest):
    deleted = await db.cleanup_oldest(req.keep)
    stats = await db.get_storage_stats()
    return {"deleted": deleted, "remaining": stats["count"], "storage_mb": stats["storage_mb"]}


@app.get("/api/health")
async def health():
    try:
        stats = await db.get_storage_stats()
    except Exception:
        stats = {}
    return {
        "status": "ok",
        "version": "4.0.0",
        "timestamp": datetime.now().isoformat(),
        "storage_mb": stats.get("storage_mb"),
        "job_count": stats.get("count"),
    }


_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
