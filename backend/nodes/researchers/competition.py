from backend.nodes.researchers.base import BaseResearcher
from backend.prompts import COMPETITION_QUERY_PROMPT


class CompetitionResearcher(BaseResearcher):
    DIMENSION    = "competition"
    QUERY_PROMPT = COMPETITION_QUERY_PROMPT

    # Two-phase search:
    # Phase 1 — find competitor homepages (with metadata like headcount, location)
    # Phase 2 — find competitive analysis articles from authoritative sources
    EXA_SEARCH_CONFIGS = [
        {
            "type":            "auto",
            "category":        "company",    # discovers competitor official pages
            "queries_override": 2,           # use first 2 queries for discovery
        },
        {
            "type": "neural",                # deep analysis articles
            "include_domains": [
                "gartner.com", "forrester.com", "mckinsey.com",
                "bain.com", "bcg.com", "hbr.org",
                "bloomberg.com", "reuters.com", "36kr.com",
            ],
            "queries_override": 2,           # use last 2 queries for analysis
        },
    ]
