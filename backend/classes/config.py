"""
Competitor Research Agent — Central Configuration
All constants, dimension configs, report type presets, and tuning parameters.
"""

from typing import Dict, List, Any

# ── Dimension registry ────────────────────────────────────────────────────────

AVAILABLE_DIMENSIONS: List[str] = [
    "product_pricing",
    "market_position",
    "traction_growth",
    "customer_sentiment",
    "content_gtm",
    "recent_activity",
]

DIMENSION_LABELS: Dict[str, str] = {
    "product_pricing":    "产品与定价",
    "market_position":    "市场定位",
    "traction_growth":    "增长与牵引力",
    "customer_sentiment": "客户评价",
    "content_gtm":        "内容与市场策略",
    "recent_activity":    "最新动态",
}

DIMENSION_LABELS_EN: Dict[str, str] = {
    "product_pricing":    "Product & Pricing",
    "market_position":    "Market Position",
    "traction_growth":    "Traction & Growth",
    "customer_sentiment": "Customer Sentiment",
    "content_gtm":        "Content & GTM",
    "recent_activity":    "Recent Activity",
}

# ── Report type configs ───────────────────────────────────────────────────────
# Each report type defines:
#   - which dimensions to research (controls Exa API cost and speed)
#   - what the comparator should focus on
#   - which default template to use

REPORT_TYPE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "full_analysis": {
        "label":            "Full Competitive Analysis",
        "description":      "Comprehensive 360° competitive intelligence across all dimensions",
        "dimensions":       AVAILABLE_DIMENSIONS,
        "comparator_focus": "all",
        "template_key":     "full_analysis",
    },
    "pricing_focus": {
        "label":            "Pricing & Product Focus",
        "description":      "Deep dive into product features and pricing models",
        "dimensions":       ["product_pricing", "market_position"],
        "comparator_focus": "pricing_and_feature",
        "template_key":     "pricing_focus",
    },
    "investor_teardown": {
        "label":            "Investor Teardown",
        "description":      "Growth metrics, fundraising, moats — built for investment decisions",
        "dimensions":       ["traction_growth", "market_position", "recent_activity"],
        "comparator_focus": "growth_and_moat",
        "template_key":     "investor_teardown",
    },
    "customer_voice": {
        "label":            "Customer Voice",
        "description":      "Review mining, sentiment analysis, and churn signals",
        "dimensions":       ["customer_sentiment", "recent_activity"],
        "comparator_focus": "sentiment_and_churn",
        "template_key":     "customer_voice",
    },
    "custom": {
        "label":            "Custom Template",
        "description":      "Upload your own template — all dimensions will be researched",
        "dimensions":       AVAILABLE_DIMENSIONS,   # always run all for custom
        "comparator_focus": "all",
        "template_key":     None,                   # user-supplied
    },
}

VALID_REPORT_TYPES: List[str] = list(REPORT_TYPE_CONFIGS.keys())

# ── Depth configs ─────────────────────────────────────────────────────────────
# Controls how many Exa queries/results per dimension.
# Drives the estimated_minutes shown in the UI tooltip.

DEPTH_CONFIGS: Dict[str, Dict[str, Any]] = {
    "snapshot": {
        "label":             "Snapshot",
        "description":       "Quick overview, great for initial exploration",
        "estimated_minutes": 5,
        "queries_per_dim":   2,
        "results_per_query": 3,
        "max_docs_per_dim":  5,
    },
    "standard": {
        "label":             "Standard",
        "description":       "Balanced and comprehensive — recommended",
        "estimated_minutes": 15,
        "queries_per_dim":   4,
        "results_per_query": 5,
        "max_docs_per_dim":  15,
    },
    "deep_dive": {
        "label":             "Deep Dive",
        "description":       "Maximum coverage, built for investment decisions",
        "estimated_minutes": 30,
        "queries_per_dim":   7,
        "results_per_query": 10,
        "max_docs_per_dim":  30,
    },
}

VALID_DEPTHS: List[str] = list(DEPTH_CONFIGS.keys())
VALID_OUTPUT_FORMATS: List[str] = ["markdown", "pdf", "json"]

# ── Competitor limits ─────────────────────────────────────────────────────────

MAX_COMPETITORS: int = 5    # hard cap on number of competitor companies
MIN_COMPETITORS: int = 1    # at least 1 competitor required to run
MAX_DISCOVERY_SUGGESTIONS: int = 5   # how many auto-discovered competitors to suggest

# ── Context size limits ───────────────────────────────────────────────────────

GROUNDING_MAX_CHARS: int   = 8_000    # max chars crawled from official website
GROUNDING_QUERY_CHARS: int = 2_000    # subset of site_scrape passed to query-gen LLM
DOC_MAX_CHARS: int         = 4_000    # max chars per document fetched by Exa
COMPARATOR_CONTEXT_MAX_CHARS: int = 80_000  # max total chars per comparator LLM call
REFERENCES_MAX: int        = 15       # max references kept in final report

# ── Exa API settings ──────────────────────────────────────────────────────────

EXA_BATCH_SIZE: int = 20             # get_contents() batch size
EXA_SCORE_THRESHOLD: float = 0.3     # minimum Exa score to keep a document

# ── Quality thresholds (Evaluator node) ───────────────────────────────────────

QUALITY_THRESHOLDS: Dict[str, Any] = {
    "min_docs_per_dimension":  3,     # flag if a company has < 3 docs for a dimension
    "min_companies_coverage":  0.6,   # flag if < 60% of companies have data for a dimension
    "min_avg_score":           0.4,   # flag if avg Exa score < 0.4 for a dimension
}

# ── Authoritative domain boosts per dimension ─────────────────────────────────
# Documents from these domains get +0.15 quality score boost in curator

AUTHORITATIVE_DOMAINS: Dict[str, List[str]] = {
    "product_pricing": [
        "g2.com", "capterra.com", "producthunt.com", "trustradius.com",
        "getapp.com", "softwareadvice.com",
    ],
    "market_position": [
        "gartner.com", "forrester.com", "idc.com", "mckinsey.com",
        "bcg.com", "hbr.org", "a16z.com",
    ],
    "traction_growth": [
        "crunchbase.com", "pitchbook.com", "bloomberg.com",
        "techcrunch.com", "reuters.com", "36kr.com",
    ],
    "customer_sentiment": [
        "g2.com", "trustpilot.com", "reddit.com", "capterra.com",
        "trustradius.com", "glassdoor.com",
    ],
    "content_gtm": [],   # no domain restriction for GTM research
    "recent_activity": [
        "techcrunch.com", "reuters.com", "bloomberg.com",
        "wsj.com", "ft.com", "36kr.com", "sina.com.cn",
    ],
}

# ── Concurrency / rate-limit settings ────────────────────────────────────────

SEMAPHORE_GROUNDING: int    = 5    # parallel company groundings
SEMAPHORE_RESEARCHERS: int  = 10   # parallel researcher tasks (N companies × M dims)
SEMAPHORE_EXA_SEARCH: int   = 8    # parallel Exa search calls inside a researcher
SEMAPHORE_COMPARATOR: int   = 3    # parallel comparator LLM calls

# ── Retry settings ────────────────────────────────────────────────────────────

MAX_RESEARCHER_RETRIES: int  = 2
RETRY_DELAY_BASE: float      = 3.0   # seconds; multiplied by attempt number
MAX_EVALUATOR_RETRIES: int   = 1     # max pipeline-level retries via evaluator gate

# ── Stale data threshold ──────────────────────────────────────────────────────

STALE_DATA_DAYS: int = 180   # flag data older than 6 months in editor output
