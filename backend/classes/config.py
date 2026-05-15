"""Shared configuration for the Market Study Agent."""

from typing import Any, Dict, List

DEPTH_CONFIGS: Dict[str, Dict[str, Any]] = {
    "snapshot": {
        "label": "Snapshot",
        "description": "快速概览，适合初筛方向。",
        "estimated_minutes": 5,
        "queries_per_theme": 2,
        "results_per_query": 3,
        "max_docs_per_theme": 5,
    },
    "standard": {
        "label": "Standard",
        "description": "均衡覆盖，默认推荐。",
        "estimated_minutes": 15,
        "queries_per_theme": 4,
        "results_per_query": 5,
        "max_docs_per_theme": 15,
    },
    "deep_dive": {
        "label": "Deep Dive",
        "description": "最大覆盖，适合正式决策材料。",
        "estimated_minutes": 30,
        "queries_per_theme": 7,
        "results_per_query": 10,
        "max_docs_per_theme": 30,
    },
}

VALID_DEPTHS: List[str] = list(DEPTH_CONFIGS.keys())
VALID_OUTPUT_FORMATS: List[str] = ["markdown", "pdf", "word"]

DOC_MAX_CHARS: int = 4_000
EXA_SCORE_THRESHOLD: float = 0.25
SEMAPHORE_EXA_SEARCH: int = 8
SEMAPHORE_THEME_AGENTS: int = 6
MAX_RESEARCHER_RETRIES: int = 2
RETRY_DELAY_BASE: float = 3.0

QUALITY_THRESHOLDS: Dict[str, Any] = {
    "min_docs_per_theme": 3,
    "min_citation_count": 3,
}
