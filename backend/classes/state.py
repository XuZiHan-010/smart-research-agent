"""
Market Study Agent state definitions.

The previous product compared many companies across fixed dimensions. This
workflow studies one market domain across selected research themes.
"""

import operator
from collections import defaultdict
from datetime import datetime
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict


class Citation(TypedDict, total=False):
    doc_id: str
    title: str
    url: str
    source: str
    published_date: Optional[str]
    excerpt: str


class StructuredTable(TypedDict, total=False):
    title: str
    markdown: str
    notes: str


class ForecastSection(TypedDict, total=False):
    historical: str
    forecast: str
    assumptions: List[str]


class ThemeReport(TypedDict, total=False):
    theme_key: str
    theme_label_zh: str
    is_custom: bool
    narrative: str
    tables: List[StructuredTable]
    citations: Dict[str, Citation]
    confidence: Literal["high", "medium", "low"]
    data_gaps: List[str]
    forecast_section: Optional[ForecastSection]
    quality_flags: List[Dict[str, Any]]


class InputState(TypedDict):
    research_domain: str
    selected_themes: List[str]
    custom_themes: List[str]
    geography: List[str]
    time_range: Dict[str, str]
    depth: Literal["snapshot", "standard", "deep_dive"]
    theme_depths: Dict[str, str]
    output_format: Literal["markdown", "pdf", "word"]
    job_id: str


class ResearchState(InputState, total=False):
    queries_per_theme: int
    results_per_query: int
    max_docs_per_theme: int
    theme_depth_params: Dict[str, Dict[str, int]]

    theme_reports: Annotated[List[ThemeReport], operator.add]
    validation_report: Optional[Dict[str, Any]]
    compacted_skeleton: Optional[Dict[str, Any]]
    final_report_md: Optional[str]
    citations_map: Optional[Dict[str, Any]]
    report: str
    output: Any

    events: Annotated[List[Dict[str, Any]], operator.add]
    error: str


job_status: Dict[str, Any] = defaultdict(lambda: {
    "status": "pending",
    "research_domain": None,
    "report": None,
    "output": None,
    "output_format": None,
    "error": None,
    "events": [],
    "last_update": datetime.now().isoformat(),
})
