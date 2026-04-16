from typing import Dict, Any, List
from backend.nodes.researchers.base import BaseResearcher
from backend.query_prompts import CUSTOMER_SENTIMENT_QUERY_PROMPT


class CustomerSentimentResearcher(BaseResearcher):
    DIMENSION    = "customer_sentiment"
    QUERY_PROMPT = CUSTOMER_SENTIMENT_QUERY_PROMPT

    EXA_SEARCH_CONFIGS: List[Dict[str, Any]] = [
        {"type": "neural"},
    ]
