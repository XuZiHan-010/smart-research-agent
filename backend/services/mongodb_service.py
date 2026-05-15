"""Async MongoDB access for the Market Study Agent."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

_client: Optional[AsyncIOMotorClient] = None


def _get_db():
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2000)
    return _client["market_study_agent"]


def _next_midnight_utc8_as_utc() -> datetime:
    """Return next-day midnight UTC+8 expressed as a UTC datetime (for TTL)."""
    now_utc8 = datetime.now(timezone.utc) + timedelta(hours=8)
    next_midnight_utc8 = (now_utc8 + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (next_midnight_utc8 - timedelta(hours=8)).replace(tzinfo=None)


async def ensure_indexes() -> None:
    db = _get_db()
    # research_jobs: TTL expires at next UTC+8 midnight (expireAfterSeconds=0 uses expires_at field)
    await db.jobs.create_index("expires_at", expireAfterSeconds=0)
    await db.clarifications.create_index("expires_at", expireAfterSeconds=0)
    await db.agent_traces.create_index([("job_id", 1), ("created_at", 1)])
    await db.checkpoints.create_index([("job_id", 1), ("theme_key", 1)], unique=True)


async def create_job(job_id: str, config: Dict[str, Any]) -> None:
    db = _get_db()
    await db.jobs.insert_one({
        "_id": job_id,
        "id": job_id,
        "research_domain": config["research_domain"],
        "selected_themes": config.get("selected_themes", []),
        "custom_themes": config.get("custom_themes", []),
        "geography": config.get("geography", []),
        "time_range": config.get("time_range", {}),
        "depth": config.get("depth", "standard"),
        "theme_depths": config.get("theme_depths", {}),
        "output_format": config.get("output_format", "markdown"),
        "created_by": config.get("created_by", "anonymous"),
        "status": "running",
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": _next_midnight_utc8_as_utc(),
        "completed_at": None,
        "theme_reports": [],
        "validation_report": {},
        "compacted_skeleton": {},
        "citations_map": {},
        "report": None,
        "report_version": 0,
        "output": None,
        "error": None,
    })


async def update_job(job_id: str, fields: Dict[str, Any]) -> None:
    db = _get_db()
    await db.jobs.update_one({"_id": job_id}, {"$set": fields})


async def complete_job(job_id: str, report: str, extra: Optional[Dict[str, Any]] = None) -> None:
    db = _get_db()
    fields = {
        "status": "completed",
        "report": report,
        "completed_at": datetime.utcnow().isoformat(),
    }
    if extra:
        fields.update(extra)
    await db.jobs.update_one({"_id": job_id}, {"$set": fields, "$inc": {"report_version": 1}})


async def fail_job(job_id: str, error: str) -> None:
    db = _get_db()
    await db.jobs.update_one(
        {"_id": job_id},
        {"$set": {
            "status": "failed",
            "error": error[:500],
            "completed_at": datetime.utcnow().isoformat(),
        }},
    )


async def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    db = _get_db()
    doc = await db.jobs.find_one({"_id": job_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    db = _get_db()
    docs = await db.jobs.find(
        {},
        {
            "_id": 0,
            "report": 0,
            "theme_reports": 0,
            "compacted_skeleton": 0,
            "citations_map": 0,
            "output": 0,
        },
    ).sort("created_at", -1).limit(limit).to_list(length=limit)
    return docs


async def delete_job(job_id: str) -> bool:
    db = _get_db()
    result = await db.jobs.delete_one({"_id": job_id})
    await db.agent_traces.delete_many({"job_id": job_id})
    await db.checkpoints.delete_many({"job_id": job_id})
    return result.deleted_count > 0


async def get_storage_stats() -> Dict[str, Any]:
    db = _get_db()
    stats = await db.command("collStats", "jobs")
    return {
        "count": stats.get("count", 0),
        "storage_bytes": stats.get("storageSize", 0),
        "storage_mb": round(stats.get("storageSize", 0) / (1024 * 1024), 2),
    }


async def cleanup_oldest(keep: int = 10) -> int:
    db = _get_db()
    recent = await db.jobs.find({}, {"_id": 1}).sort("created_at", -1).limit(keep).to_list(length=keep)
    keep_ids = {doc["_id"] for doc in recent}
    if not keep_ids:
        return 0
    to_delete = await db.jobs.find({"_id": {"$nin": list(keep_ids)}}, {"_id": 1}).to_list(length=10000)
    delete_ids = [doc["_id"] for doc in to_delete]
    if not delete_ids:
        return 0
    result = await db.jobs.delete_many({"_id": {"$in": delete_ids}})
    # Cascade delete associated data
    await db.agent_traces.delete_many({"job_id": {"$in": delete_ids}})
    await db.checkpoints.delete_many({"job_id": {"$in": delete_ids}})
    return result.deleted_count


async def save_clarification(clarification_id: str, payload: Dict[str, Any]) -> None:
    db = _get_db()
    await db.clarifications.update_one(
        {"_id": clarification_id},
        {"$set": {
            **payload,
            "_id": clarification_id,
            "id": clarification_id,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": datetime.utcnow() + timedelta(hours=24),
        }},
        upsert=True,
    )


async def get_clarification(clarification_id: str) -> Optional[Dict[str, Any]]:
    db = _get_db()
    doc = await db.clarifications.find_one({"_id": clarification_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def save_checkpoint(job_id: str, theme_key: str, payload: Dict[str, Any]) -> None:
    db = _get_db()
    await db.checkpoints.update_one(
        {"job_id": job_id, "theme_key": theme_key},
        {"$set": {
            "job_id": job_id,
            "theme_key": theme_key,
            "payload": payload,
            "updated_at": datetime.utcnow().isoformat(),
        }},
        upsert=True,
    )


async def get_checkpoints(job_id: str) -> Dict[str, Dict[str, Any]]:
    db = _get_db()
    docs = await db.checkpoints.find({"job_id": job_id}).to_list(length=100)
    return {doc["theme_key"]: doc.get("payload", {}) for doc in docs}


async def record_trace(job_id: str, trace: Dict[str, Any]) -> None:
    db = _get_db()
    await db.agent_traces.insert_one({
        "job_id": job_id,
        "created_at": datetime.utcnow().isoformat(),
        **trace,
    })


async def get_traces(job_id: str) -> List[Dict[str, Any]]:
    db = _get_db()
    docs = await db.agent_traces.find({"job_id": job_id}, {"_id": 0}).sort("created_at", 1).to_list(length=500)
    return docs
