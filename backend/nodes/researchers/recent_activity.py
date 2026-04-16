from typing import Dict, Any, List
from backend.nodes.researchers.base import BaseResearcher
from backend.query_prompts import RECENT_ACTIVITY_QUERY_PROMPT


class RecentActivityResearcher(BaseResearcher):
    DIMENSION    = "recent_activity"
    QUERY_PROMPT = RECENT_ACTIVITY_QUERY_PROMPT

    EXA_SEARCH_CONFIGS: List[Dict[str, Any]] = [
        {
            "type":                 "neural",
            "category":             "news",
            "start_published_date": "dynamic",
        },
        {
            "type": "neural",
            "include_domains": [
                "techcrunch.com", "reuters.com", "bloomberg.com",
                "wsj.com", "ft.com", "36kr.com",
            ],
            "queries_override": 2,
        },
    ]
