from backend.nodes.researchers.base import BaseResearcher
from backend.prompts import COMPANY_OVERVIEW_QUERY_PROMPT


class CompanyResearcher(BaseResearcher):
    DIMENSION    = "company_overview"
    QUERY_PROMPT = COMPANY_OVERVIEW_QUERY_PROMPT

    # category="company" returns official homepages with rich metadata
    # (employee count, location, funding) — no domain/date filters allowed
    EXA_SEARCH_CONFIGS = [
        {"type": "auto", "category": "company"},
    ]
