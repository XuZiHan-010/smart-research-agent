from typing import Dict, Any, List
from backend.nodes.researchers.base import BaseResearcher
from backend.query_prompts import CONTENT_GTM_QUERY_PROMPT


class ContentGTMResearcher(BaseResearcher):
    DIMENSION    = "content_gtm"
    QUERY_PROMPT = CONTENT_GTM_QUERY_PROMPT

    EXA_SEARCH_CONFIGS: List[Dict[str, Any]] = [
        {"type": "neural"},
    ]
