from backend.nodes.researchers.base import BaseResearcher
from backend.prompts import TEAM_SIZE_QUERY_PROMPT


class TeamResearcher(BaseResearcher):
    DIMENSION    = "team_and_size"
    QUERY_PROMPT = TEAM_SIZE_QUERY_PROMPT

    # Two-phase: LinkedIn profiles + company pages with headcount data
    EXA_SEARCH_CONFIGS = [
        {"type": "neural", "category": "people",  "queries_override": 2},
        {"type": "neural", "category": "company", "queries_override": 2},
    ]
