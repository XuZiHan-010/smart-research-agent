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

# Hard upper bound on the docs_text payload sent to the theme report writer.
# CN-heavy content ≈ 1 token / char. Keeping docs_text ≤ ~22K chars leaves
# headroom for the ~2K-token system prompt + ~3K-token expected output so
# the total stays under the 30K TPM of OpenAI Tier 1 for gpt-4.1.
WRITER_DOCS_CHAR_BUDGET: int = 22_000
# Per-document excerpt cap inside docs_text. Prevents a single very long
# article from eating the whole budget and pushing out diverse sources.
WRITER_PER_DOC_EXCERPT_LIMIT: int = 2_400
SEMAPHORE_EXA_SEARCH: int = 8
# Theme concurrency. Lower than #themes to stay within OpenAI gpt-4.1 TPM.
# Tier 1 gpt-4.1 TPM ≈ 30K; each theme report writer call sends ~10K tokens
# (input ~6K + output ~3K + overhead). With concurrency=2 the simultaneous
# token usage stays under 20K, leaving headroom for the quality-gate retry.
SEMAPHORE_THEME_AGENTS: int = 2
MAX_RESEARCHER_RETRIES: int = 2
RETRY_DELAY_BASE: float = 3.0

# Exponential backoff for LLM rate-limit (429) errors inside ThemeSubAgent.
# Each retry waits LLM_RATELIMIT_BACKOFF_BASE * 2**(attempt-1) seconds before
# giving up after LLM_RATELIMIT_MAX_RETRIES total attempts.
LLM_RATELIMIT_MAX_RETRIES: int = 4
LLM_RATELIMIT_BACKOFF_BASE: float = 8.0

QUALITY_THRESHOLDS: Dict[str, Any] = {
    "min_docs_per_theme": 3,
    "min_citation_count": 3,
}
