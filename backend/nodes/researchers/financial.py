from backend.nodes.researchers.base import BaseResearcher
from backend.prompts import FINANCIAL_QUERY_PROMPT


class FinancialResearcher(BaseResearcher):
    DIMENSION    = "financial"
    QUERY_PROMPT = FINANCIAL_QUERY_PROMPT

    EXA_SEARCH_CONFIGS = [
        {
            "type": "neural",
            "include_domains": [
                "crunchbase.com", "pitchbook.com", "bloomberg.com",
                "techcrunch.com", "reuters.com", "ft.com",
                "wsj.com", "36kr.com", "sina.com.cn",
            ],
        },
    ]
