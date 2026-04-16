from backend.nodes.researchers.base import BaseResearcher
from backend.prompts import INDUSTRY_QUERY_PROMPT


class IndustryResearcher(BaseResearcher):
    DIMENSION    = "industry"
    QUERY_PROMPT = INDUSTRY_QUERY_PROMPT

    EXA_SEARCH_CONFIGS = [
        {
            "type": "neural",
            "include_domains": [
                "statista.com", "ibisworld.com", "mordorintelligence.com",
                "grandviewresearch.com", "mckinsey.com", "deloitte.com",
                "pwc.com", "marketresearch.com",
            ],
        },
    ]
