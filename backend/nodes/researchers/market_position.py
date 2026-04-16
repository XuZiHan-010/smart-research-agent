from typing import Dict, Any, List
from backend.nodes.researchers.base import BaseResearcher
from backend.query_prompts import MARKET_POSITION_QUERY_PROMPT


class MarketPositionResearcher(BaseResearcher):
    DIMENSION    = "market_position"
    QUERY_PROMPT = MARKET_POSITION_QUERY_PROMPT

    EXA_SEARCH_CONFIGS: List[Dict[str, Any]] = [
        {"type": "neural"},
        {
            "type": "neural",
            "include_domains": [
                "gartner.com", "forrester.com", "idc.com",
                "hbr.org", "bloomberg.com", "reuters.com",
            ],
            "queries_override": 1,
        },
    ]
