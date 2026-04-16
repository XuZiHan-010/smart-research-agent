"""
MongoDB Service — async CRUD for the competitor research agent.

Schema (one document per job):
  _id / id          : job_id (UUID string)
  target_company    : str
  target_website    : str
  competitors       : [str]            user-provided names
  all_companies     : [{name,website}] confirmed after discovery
  report_type       : str
  depth             : str
  output_format     : str
  template          : str              "" = system default
  status            : pending|running|completed|failed
  created_at        : ISO datetime
  completed_at      : ISO datetime | None

  # intermediate products (written by each node, read by later nodes)
  curated_company_data : {company: {dimension: [{url,title,score,content,...}]}}
  comparisons          : {dimension: str}
  battlecard_data      : {...}

  # final output
  report         : str
  report_version : int            incremented on each edit
  output         : str | None     PDF bytes stored separately if needed

  # edit audit
  edit_history   : [{instruction, mode, timestamp, version}]

  error          : str | None
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

_client: Optional[AsyncIOMotorClient] = None


def _get_db():
    global _client
    if _client is None:
        uri     = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        _client = AsyncIOMotorClient(uri)
    return _client["competitor_research_agent"]


# ── Job lifecycle ─────────────────────────────────────────────────────────────

async def create_job(job_id: str, config: Dict[str, Any]) -> None:
    db = _get_db()
    await db.jobs.insert_one({
        "_id":           job_id,
        "id":            job_id,
        "target_company": config["target_company"],
        "target_website": config.get("target_website", ""),
        "competitors":    config.get("competitors", []),
        "all_companies":  config.get("all_companies", []),
        "report_type":    config.get("report_type", "full_analysis"),
        "depth":          config.get("depth", "standard"),
        "output_format":  config.get("output_format", "markdown"),
        "template":       config.get("template", ""),
        "status":         "running",
        "created_at":     datetime.utcnow().isoformat(),
        "completed_at":   None,
        # intermediate products
        "curated_company_data": {},
        "comparisons":          {},
        "battlecard_data":      {},
        # final output
        "report":         None,
        "report_version": 0,
        "output":         None,
        # edit audit
        "edit_history":   [],
        "error":          None,
    })


async def update_job(job_id: str, fields: Dict[str, Any]) -> None:
    """Generic partial update — pass only the fields that changed."""
    db = _get_db()
    await db.jobs.update_one({"_id": job_id}, {"$set": fields})


async def complete_job(job_id: str, report: str) -> None:
    db = _get_db()
    await db.jobs.update_one(
        {"_id": job_id},
        {"$set": {
            "status":       "completed",
            "report":       report,
            "completed_at": datetime.utcnow().isoformat(),
        }, "$inc": {"report_version": 1}},
    )


async def fail_job(job_id: str, error: str) -> None:
    db = _get_db()
    await db.jobs.update_one(
        {"_id": job_id},
        {"$set": {
            "status":       "failed",
            "error":        error[:500],
            "completed_at": datetime.utcnow().isoformat(),
        }},
    )


# ── Intermediate product reads (used by comparator / battlecard / editor) ─────

async def get_dimension_data(
    job_id: str,
    dimension: str,
    companies: Optional[List[str]] = None,
) -> Dict[str, List[Dict]]:
    """
    Load curated docs for one dimension across all (or specified) companies.
    Returns {company_name: [doc, ...]}
    Comparator calls this once per dimension to avoid loading all data at once.
    """
    db  = _get_db()
    doc = await db.jobs.find_one(
        {"_id": job_id},
        {"curated_company_data": 1},
    )
    if not doc:
        return {}

    all_data = doc.get("curated_company_data", {})
    result: Dict[str, List[Dict]] = {}
    for company, dims in all_data.items():
        if companies and company not in companies:
            continue
        if dimension in dims:
            result[company] = dims[dimension]
    return result


async def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    db  = _get_db()
    doc = await db.jobs.find_one({"_id": job_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    db   = _get_db()
    docs = await db.jobs.find(
        {},
        {
            "_id": 0,
            "report": 0,                    # exclude heavy body from list
            "curated_company_data": 0,       # exclude intermediate data
            "comparisons": 0,
        },
    ).sort("created_at", -1).limit(limit).to_list(length=limit)
    return docs


async def append_edit_history(
    job_id: str,
    instruction: str,
    mode: str,
    version: int,
) -> None:
    db = _get_db()
    await db.jobs.update_one(
        {"_id": job_id},
        {"$push": {"edit_history": {
            "instruction": instruction,
            "mode":        mode,
            "timestamp":   datetime.utcnow().isoformat(),
            "version":     version,
        }}},
    )


async def delete_job(job_id: str) -> bool:
    db     = _get_db()
    result = await db.jobs.delete_one({"_id": job_id})
    return result.deleted_count > 0


async def get_storage_stats() -> Dict[str, Any]:
    """Return collection stats: document count and approximate storage size in bytes."""
    db = _get_db()
    stats = await db.command("collStats", "jobs")
    return {
        "count":        stats.get("count", 0),
        "storage_bytes": stats.get("storageSize", 0),
        "storage_mb":   round(stats.get("storageSize", 0) / (1024 * 1024), 2),
    }


async def cleanup_oldest(keep: int = 10) -> int:
    """
    Delete the oldest jobs beyond the `keep` threshold.
    Returns the number of deleted documents.

    Strategy: keep the N most recent jobs, delete the rest.
    This is safe for the 512MB free tier — called on-demand or before each new job.
    """
    db = _get_db()
    # Find the IDs of the most recent `keep` jobs
    recent = await db.jobs.find(
        {}, {"_id": 1}
    ).sort("created_at", -1).limit(keep).to_list(length=keep)
    keep_ids = {doc["_id"] for doc in recent}

    if not keep_ids:
        return 0

    result = await db.jobs.delete_many({"_id": {"$nin": list(keep_ids)}})
    return result.deleted_count
