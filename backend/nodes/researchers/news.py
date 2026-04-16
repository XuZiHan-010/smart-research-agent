from backend.nodes.researchers.base import BaseResearcher
from backend.prompts import NEWS_QUERY_PROMPT


class NewsResearcher(BaseResearcher):
    DIMENSION    = "news"
    QUERY_PROMPT = NEWS_QUERY_PROMPT

    # category="news" + dynamic date filter = only last 6 months
    EXA_SEARCH_CONFIGS = [
        {
            "type":                 "neural",
            "category":             "news",
            "start_published_date": "dynamic",   # resolved to 6 months ago in base
        },
    ]
