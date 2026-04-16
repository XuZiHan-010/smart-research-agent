from typing import Dict, Any, List
from backend.nodes.researchers.base import BaseResearcher
from backend.query_prompts import TRACTION_GROWTH_QUERY_PROMPT


class TractionGrowthResearcher(BaseResearcher):
    DIMENSION    = "traction_growth"
    QUERY_PROMPT = TRACTION_GROWTH_QUERY_PROMPT

    EXA_SEARCH_CONFIGS: List[Dict[str, Any]] = [
        {"type": "neural"},
    ]
