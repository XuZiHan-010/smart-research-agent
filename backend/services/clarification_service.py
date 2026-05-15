"""Round 1 questionnaire builder."""

import uuid
from datetime import datetime
from typing import Any, Dict

from backend.classes.market_study_config import GEOGRAPHY_OPTIONS, MARKET_THEMES
from backend.services import mongodb_service as db


def _month(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def _shift_years(dt: datetime, years: int) -> datetime:
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        return dt.replace(month=2, day=28, year=dt.year + years)


async def build_questionnaire(confirmed_domain: str) -> Dict[str, Any]:
    today = datetime.utcnow()
    clarification_id = str(uuid.uuid4())
    payload: Dict[str, Any] = {
        "clarification_id": clarification_id,
        "research_domain": confirmed_domain.strip(),
        "themes": [{**theme, "checked": True} for theme in MARKET_THEMES],
        "custom_themes_max": 3,
        "geography_options": [dict(option) for option in GEOGRAPHY_OPTIONS],
        "time_range": {
            "start": _month(_shift_years(today, -5)),
            "end": _month(_shift_years(today, 5)),
            "today": _month(today),
        },
    }
    await db.save_clarification(clarification_id, payload)
    return payload
