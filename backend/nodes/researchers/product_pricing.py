from typing import Dict, Any, List
from backend.nodes.researchers.base import BaseResearcher
from backend.query_prompts import PRODUCT_PRICING_QUERY_PROMPT


class ProductPricingResearcher(BaseResearcher):
    DIMENSION    = "product_pricing"
    QUERY_PROMPT = PRODUCT_PRICING_QUERY_PROMPT

    EXA_SEARCH_CONFIGS: List[Dict[str, Any]] = [
        {"type": "neural"},
    ]
