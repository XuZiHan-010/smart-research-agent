"""
FastAPI server — Competitor Research Agent

Endpoints:
  POST   /api/research/discover           → auto-discover competitor suggestions
  POST   /api/research/start              → launch research pipeline, returns job_id
  GET    /api/research/{id}/stream        → SSE real-time events
  GET    /api/research/{id}/report        → get completed report + battlecard
  GET    /api/research/{id}/battlecard    → get battlecard data only
  POST   /api/research/{id}/edit          → edit existing report (3 modes)
  GET    /api/research/{id}/download      → download as md | pdf | json
  GET    /api/research/history            → list past jobs
  DELETE /api/research/{id}              → delete a job record
  GET    /api/health                      → health check

Architecture:
  - Graph runs as a FastAPI BackgroundTask
  - Events are pushed into job_status[job_id]["events"] (FIFO list)
  - SSE endpoint drains the list continuously until status = completed/failed
  - MongoDB is the source of truth; in-memory job_status is ephemeral (SSE + progress)
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import os

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.classes.config import VALID_REPORT_TYPES, VALID_DEPTHS
from backend.classes.state import job_status
from backend.graph import Graph
from backend.services import mongodb_service as db
from backend.services.discovery_service import discover_competitors

load_dotenv()

app = FastAPI(title="Competitor Research Agent API", version="3.0.0")

_EXTRA_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"(https?://)?(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.up\.railway\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_caller_email(request: Request) -> str:
    """
    Cloudflare Access injects the authenticated user's email into
    the 'Cf-Access-Authenticated-User-Email' header.
    Falls back to 'anonymous' when running locally or without Cloudflare.
    """
    return request.headers.get("Cf-Access-Authenticated-User-Email", "anonymous")


# ── Company name normalisation ────────────────────────────────────────────────

# Well-known names whose casing cannot be derived via str.title()
_CASE_OVERRIDES = {
    "3m": "3M", "ibm": "IBM", "sap": "SAP", "bmw": "BMW", "ups": "UPS",
    "lg": "LG", "hp": "HP", "ge": "GE", "bp": "BP", "ai": "AI",
    "h.b. fuller": "H.B. Fuller", "rpm international inc.": "RPM International Inc.",
}


def _normalize_company_name(name: str) -> str:
    """Title-case a company name, respecting well-known abbreviations."""
    stripped = name.strip()
    if not stripped:
        return stripped
    lower = stripped.lower()
    if lower in _CASE_OVERRIDES:
        return _CASE_OVERRIDES[lower]
    # title() handles "henkel" → "Henkel", "sika ag" → "Sika Ag"
    # Fix common suffixes that title() gets wrong
    result = stripped.title()
    for suffix in (" Ag", " Ab", " Sa", " Se", " Nv", " Plc", " Inc", " Ltd", " Llc", " Gmbh"):
        if result.endswith(suffix):
            result = result[: -len(suffix)] + suffix.upper()
    return result


# ── Request / Response models ─────────────────────────────────────────────────

class DiscoverRequest(BaseModel):
    target_company:  str
    target_website:  str = ""
    competitors:     List[str] = Field(default_factory=list)


class CompanyInput(BaseModel):
    name:    str
    website: str = ""
    source:  str = "user"   # "user" | "discovered" | "target"


class ResearchRequest(BaseModel):
    target_company:  str
    target_website:  str = ""
    all_companies:   List[CompanyInput]   # confirmed list after discovery
    report_type:     str = "full_analysis"
    depth:           str = "standard"
    output_format:   str = "markdown"
    language:        str = "en"
    template:        str = ""


class EditRequest(BaseModel):
    edit_mode:        str   # "quick_edit" | "targeted_refresh" | "full_refresh"
    edit_instruction: str   # free-text user instruction


# ── Background task helpers ───────────────────────────────────────────────────

async def _run_pipeline(job_id: str, graph: Graph) -> None:
    """
    Runs the LangGraph pipeline as a background task.
    Drains the event generator and pushes events into job_status for the SSE endpoint.
    """
    job_status[job_id]["status"] = "processing"
    try:
        async for event in graph.run():
            job_status[job_id]["events"].append(event)

        final = graph.get_final_state()
        report = final.get("report", "")

        job_status[job_id].update({
            "status":      "completed",
            "report":      report,
            "output":      final.get("output"),
            "last_update": datetime.now().isoformat(),
        })
        await db.complete_job(job_id, report)

    except Exception as exc:
        error = str(exc)
        job_status[job_id].update({
            "status":      "failed",
            "error":       error,
            "last_update": datetime.now().isoformat(),
        })
        await db.fail_job(job_id, error)


async def _run_quick_edit(job_id: str, existing_job: Dict, req: EditRequest) -> None:
    """
    Quick edit: pass the existing report + edit instruction directly to the
    editor node — no LangGraph overhead, no new research.
    """
    from backend.nodes.editor import editor_node

    job_status[job_id]["status"] = "processing"
    try:
        # Build a minimal state for the editor node
        all_companies = [
            {"name": c, "website": "", "source": "user"}
            for c in existing_job.get("all_companies", [])
        ]
        comparisons = existing_job.get("comparisons", {})
        # active_dimensions is set by router_node in LangGraph state but not persisted
        # to MongoDB. Fall back to comparisons.keys() so editor has the right dims.
        active_dimensions = (
            existing_job.get("active_dimensions")
            or list(comparisons.keys())
        )

        pseudo_state: Dict[str, Any] = {
            "target_company":    existing_job.get("target_company", ""),
            "all_companies":     all_companies,
            "active_dimensions": active_dimensions,
            "comparisons":       comparisons,
            "battlecard_data":   existing_job.get("battlecard_data", {}),
            "references":        existing_job.get("references", []),
            "report_type":       existing_job.get("report_type", "full_analysis"),
            "default_template":  "",
            "comparator_focus":  "",
            "curated_ref":       job_id,
            # edit fields
            "edit_mode":        req.edit_mode,
            "edit_instruction": req.edit_instruction,
            "report":           existing_job.get("report", ""),
            "report_version":   existing_job.get("report_version", 0),
            "events":           [],
        }
        delta = await editor_node(pseudo_state)
        for event in delta.get("events", []):
            job_status[job_id]["events"].append(event)

        report = delta.get("report", "")
        job_status[job_id].update({
            "status":      "completed",
            "report":      report,
            "last_update": datetime.now().isoformat(),
        })
        await db.complete_job(job_id, report)

    except Exception as exc:
        error = str(exc)
        job_status[job_id].update({
            "status":      "failed",
            "error":       error,
            "last_update": datetime.now().isoformat(),
        })
        await db.fail_job(job_id, error)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/api/research/discover")
async def discover(req: DiscoverRequest):
    """
    Auto-discover competitor suggestions for the target company.
    The client shows a DiscoveryPanel for the user to confirm / deselect.
    Only call this when the user has < 4 confirmed competitors.
    """
    req.target_company = _normalize_company_name(req.target_company)

    if len(req.competitors) >= 4:
        return {"suggestions": [], "skipped": True,
                "reason": "Already 4+ competitors provided"}

    suggestions = await discover_competitors(
        target_company  = req.target_company,
        target_website  = req.target_website,
        existing_names  = req.competitors,
    )
    return {"suggestions": suggestions}


@app.post("/api/research/start")
async def start_research(req: ResearchRequest, background_tasks: BackgroundTasks, request: Request):
    """
    Validate inputs, create a MongoDB job record, and launch the pipeline.
    The caller should have already confirmed all_companies via /discover.
    """
    if req.report_type not in VALID_REPORT_TYPES:
        raise HTTPException(400, f"Invalid report_type: {req.report_type}. "
                                 f"Valid: {VALID_REPORT_TYPES}")
    if req.depth not in VALID_DEPTHS:
        raise HTTPException(400, f"Invalid depth: {req.depth}. "
                                 f"Valid: {VALID_DEPTHS}")
    if not req.all_companies:
        raise HTTPException(400, "all_companies must include at least the target company")

    job_id = str(uuid.uuid4())

    # Normalise company names (e.g. "henkel" → "Henkel")
    req.target_company = _normalize_company_name(req.target_company)

    # Mark target company explicitly so graph can identify it
    companies = [c.model_dump() for c in req.all_companies]
    for c in companies:
        c["name"] = _normalize_company_name(c["name"])

    # Auto-cleanup: keep last 20 jobs to stay within 512MB free tier
    try:
        await db.cleanup_oldest(keep=20)
    except Exception:
        pass  # non-critical — proceed even if cleanup fails

    # Create MongoDB record immediately so /stream can poll it
    try:
        await db.create_job(job_id, {
            "target_company":  req.target_company,
            "target_website":  req.target_website,
            "competitors":     [c["name"] for c in companies if c["source"] != "target"],
            "all_companies":   companies,
            "report_type":     req.report_type,
            "depth":           req.depth,
            "output_format":   req.output_format,
            "language":        req.language,
            "template":        req.template,
            "created_by":      _get_caller_email(request),
        })
    except Exception as db_exc:
        raise HTTPException(503, detail=f"Database unavailable — cannot start job: {db_exc}")

    job_status[job_id]["status"] = "pending"

    graph = Graph(
        target_company  = req.target_company,
        target_website  = req.target_website,
        all_companies   = companies,
        report_type     = req.report_type,
        depth           = req.depth,
        output_format   = req.output_format,
        language        = req.language,
        template        = req.template,
        job_id          = job_id,
    )

    background_tasks.add_task(_run_pipeline, job_id, graph)

    return {
        "job_id":          job_id,
        "target_company":  req.target_company,
        "companies_count": len(companies),
        "report_type":     req.report_type,
        "depth":           req.depth,
    }


@app.get("/api/research/{job_id}/stream")
async def stream_research(job_id: str):
    """
    SSE endpoint — yields pipeline events in real-time.
    Events are dicts with at least {type: str}. Known types:
      status   — node progress message
      todo     — N×M progress matrix update
      stream   — editor token chunk
      complete — final report ready
      error    — pipeline failed
    """
    if job_id not in job_status:
        # Check MongoDB — job may have completed in a previous session
        job = await db.get_job(job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        # Reconstruct minimal in-memory record
        status = job.get("status", "unknown")
        if status == "completed":
            async def _replay():
                payload = json.dumps({
                    "type":   "complete",
                    "job_id": job_id,
                    "report": job.get("report", ""),
                })
                yield f"data: {payload}\n\n"
            return StreamingResponse(
                _replay(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        raise HTTPException(404, "Job not found in active session")

    async def _generator():
        # Wait up to 5 s for the background task to transition from pending
        for _ in range(50):
            if job_status[job_id]["status"] != "pending":
                break
            await asyncio.sleep(0.1)

        while True:
            status = job_status[job_id]["status"]
            events = job_status[job_id]["events"]

            # Drain accumulated events
            while events:
                evt = events.pop(0)
                yield f"data: {json.dumps(evt)}\n\n"

            if status == "completed":
                payload = json.dumps({
                    "type":   "complete",
                    "job_id": job_id,
                    "report": job_status[job_id].get("report", ""),
                })
                yield f"data: {payload}\n\n"
                break

            if status == "failed":
                payload = json.dumps({
                    "type":    "error",
                    "job_id":  job_id,
                    "message": job_status[job_id].get("error", "Unknown error"),
                })
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
    """Get completed report + metadata. Returns 202 if still processing."""
    job = await db.get_job(job_id)
    if not job:
        mem = job_status.get(job_id)
        if not mem:
            raise HTTPException(404, "Job not found")
        status = mem.get("status", "unknown")
        if status == "completed":
            return {"status": "completed", "report": mem.get("report", "")}
        elif status == "failed":
            raise HTTPException(500, mem.get("error", "Unknown error"))
        return JSONResponse(status_code=202,
                            content={"status": status, "message": "Still processing"})

    status = job.get("status", "unknown")
    if status == "completed":
        return {
            "status":       "completed",
            "job_id":       job_id,
            "target_company": job.get("target_company"),
            "report_type":  job.get("report_type"),
            "depth":        job.get("depth"),
            "report":       job.get("report", ""),
            "report_version": job.get("report_version", 1),
            "created_at":   job.get("created_at"),
            "completed_at": job.get("completed_at"),
        }
    elif status == "failed":
        raise HTTPException(500, job.get("error", "Unknown error"))
    return JSONResponse(status_code=202,
                        content={"status": status, "message": "Still processing"})


@app.get("/api/research/{job_id}/battlecard")
async def get_battlecard(job_id: str):
    """Return the structured battlecard JSON for a completed job."""
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "completed":
        raise HTTPException(425, "Battlecard not ready — job still processing")
    battlecard = job.get("battlecard_data", {})
    return {"job_id": job_id, "battlecard": battlecard}


@app.post("/api/research/{job_id}/edit")
async def edit_report(
    job_id: str,
    req:    EditRequest,
    background_tasks: BackgroundTasks,
):
    """
    Edit an existing report.

    Modes:
      quick_edit       — apply user instruction to existing text, no new research
      targeted_refresh — re-run only sections with new data (currently full pipeline)
      full_refresh     — full pipeline re-run with edit instruction

    quick_edit is handled directly (editor node only, fast).
    targeted/full refresh launch the full LangGraph pipeline with edit_mode set.
    """
    VALID_EDIT_MODES = {"quick_edit", "targeted_refresh", "full_refresh"}
    if req.edit_mode not in VALID_EDIT_MODES:
        raise HTTPException(400, f"Invalid edit_mode: {req.edit_mode}")

    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("status") != "completed":
        raise HTTPException(409, "Cannot edit a job that has not completed")

    # Reuse same job_id — the edit writes to the same MongoDB document
    job_status[job_id]["status"] = "pending"
    job_status[job_id]["events"] = []

    if req.edit_mode == "quick_edit":
        background_tasks.add_task(_run_quick_edit, job_id, job, req)
    else:
        # Full pipeline with edit_mode set — existing comparisons/battlecard reused
        companies = job.get("all_companies", [])
        if isinstance(companies[0], str) if companies else False:
            # Legacy: all_companies stored as name strings
            companies = [{"name": n, "website": "", "source": "user"}
                         for n in companies]

        graph = Graph(
            target_company    = job.get("target_company", ""),
            target_website    = job.get("target_website", ""),
            all_companies     = companies,
            report_type       = job.get("report_type", "full_analysis"),
            depth             = job.get("depth", "standard"),
            output_format     = job.get("output_format", "markdown"),
            template          = job.get("template", ""),
            job_id            = job_id,
            edit_mode         = req.edit_mode,
            edit_instruction  = req.edit_instruction,
            report            = job.get("report", ""),
            report_version    = job.get("report_version", 0),
        )
        background_tasks.add_task(_run_pipeline, job_id, graph)

    return {"job_id": job_id, "edit_mode": req.edit_mode, "status": "processing"}


@app.get("/api/research/{job_id}/download")
async def download_report(
    job_id: str,
    format: str = Query("markdown", description="markdown | pdf | json"),
):
    """Download the final report in the requested format."""
    job = await db.get_job(job_id)
    if not job or not job.get("report"):
        raise HTTPException(404, "Report not found")

    company   = job.get("target_company", "report")
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in company)
    report    = job["report"]

    if format == "pdf":
        from backend.services.pdf_service import PDFService
        language = job.get("language", "en")
        ok, result = PDFService().generate_pdf_bytes(report, company, language=language)
        if not ok:
            raise HTTPException(500, f"PDF generation failed: {result}")
        return Response(
            content=result,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
        )

    if format == "json":
        payload = json.dumps({
            "job_id":          job_id,
            "target_company":  company,
            "competitors":     job.get("competitors", []),
            "report_type":     job.get("report_type"),
            "depth":           job.get("depth"),
            "created_at":      job.get("created_at"),
            "report_version":  job.get("report_version", 1),
            "battlecard":      job.get("battlecard_data", {}),
            "comparisons":     job.get("comparisons", {}),
            "report_markdown": report,
        }, ensure_ascii=False, indent=2)
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.json"'},
        )

    # Default: markdown
    return Response(
        content=report,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.md"'},
    )


@app.get("/api/research/history")
async def get_history(limit: int = Query(50, ge=1, le=200)):
    """List past jobs from MongoDB (newest first). Heavy fields excluded."""
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


@app.post("/api/research/cleanup")
async def cleanup_storage(keep: int = Query(10, ge=1, le=100)):
    """
    Delete oldest jobs beyond the `keep` threshold.
    Call manually or let the system auto-cleanup before each new job.
    """
    deleted = await db.cleanup_oldest(keep)
    stats   = await db.get_storage_stats()
    return {"deleted": deleted, "remaining": stats["count"], "storage_mb": stats["storage_mb"]}


@app.get("/api/health")
async def health():
    try:
        stats = await db.get_storage_stats()
    except Exception:
        stats = {}
    return {
        "status":     "ok",
        "version":    "3.0.0",
        "timestamp":  datetime.now().isoformat(),
        "storage_mb": stats.get("storage_mb"),
        "job_count":  stats.get("count"),
    }


# ── Serve React build (production) ───────────────────────────────────────────

_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
