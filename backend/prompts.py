"""
All LLM prompts for the Competitor Research Agent.

Sections:
  1. Comparator prompts (Gemini 2.5 Flash)
  2. Battlecard prompt (GPT-4.1-mini)
  3. Editor prompts (GPT-4.1)
"""

from langchain_core.prompts import ChatPromptTemplate


_COMPARATOR_RULES = """
Rules:
- Base every claim on provided excerpts only; never invent facts.
- Start with market lens and comparison basis before conclusions.
- Include concrete numbers whenever present (revenue, growth, pricing, ratings, dates).
- Cite sources inline using the format (Source Name, Month Year) — e.g. (Reuters, Mar 2025) or (Henkel Annual Report, 2025). NEVER use bare numeric references like (1), (8), or [3].
- If data is sparse, state it explicitly instead of padding.
- If pricing evidence is largely missing, explicitly say:
  "Public pricing unavailable for large parts of the market."
- Keep output concise, structured, and consultant-grade in markdown.
"""

_COMPARATOR_HUMAN_BLOCK = """Compare **{target_company}** against: {competitors}
Focus hint: {comparator_focus}

Comparison basis:
{comparison_basis}

Competitor rationale:
{competitor_rationale_text}

Research data (one section per company):
{dimension_data}
"""


PRODUCT_PRICING_COMPARATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            f"""You are a product intelligence analyst writing a cross-company comparison.
Adapt to the company type reflected in evidence:
- SaaS: tiers, packaging, free-vs-paid, per-seat/usage, enterprise motion.
- Industrial/B2B materials: product lines, specs, quote-based pricing, distributor/direct channels.
- Consumer: SKU ranges, pack sizes, RRP, retail channel differences.
{_COMPARATOR_RULES}""",
        ),
        (
            "human",
            _COMPARATOR_HUMAN_BLOCK
            + """
Write:
1. Portfolio overlap and product differentiation
2. Pricing transparency, entry points, procurement model, enterprise motion
3. Where {target_company} wins and where it lags
""",
        ),
    ]
)

MARKET_POSITION_COMPARATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            f"""You are a market intelligence analyst.
Focus on positioning, segments, brand perception, analyst mentions, and share signals.
{_COMPARATOR_RULES}""",
        ),
        (
            "human",
            _COMPARATOR_HUMAN_BLOCK
            + """
Write:
1. Positioning map and segment focus
2. Industry/analyst recognition and visibility
3. Strategic implications for {target_company}
""",
        ),
    ]
)

TRACTION_GROWTH_COMPARATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            f"""You are a growth analyst.
Use metrics appropriate to company type (public enterprise, private, startup) and avoid forcing irrelevant KPI frames.
{_COMPARATOR_RULES}""",
        ),
        (
            "human",
            _COMPARATOR_HUMAN_BLOCK
            + """
Write:
1. Scale and growth evidence
2. Strategic moves (M&A, expansion, partnerships)
3. Momentum comparison and implications for {target_company}
""",
        ),
    ]
)

CUSTOMER_SENTIMENT_COMPARATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            f"""You are a customer intelligence analyst.
Use sentiment sources appropriate to company type (SaaS review platforms, industrial references, or consumer channels).
{_COMPARATOR_RULES}""",
        ),
        (
            "human",
            _COMPARATOR_HUMAN_BLOCK
            + """
Write:
1. Overall sentiment and evidence sources
2. Repeated strengths and complaints
3. Sentiment risks/opportunities for {target_company}
""",
        ),
    ]
)

CONTENT_GTM_COMPARATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            f"""You are a GTM strategist.
Compare sales motion, content strategy, channel ecosystem, and go-to-market execution signals.
{_COMPARATOR_RULES}""",
        ),
        (
            "human",
            _COMPARATOR_HUMAN_BLOCK
            + """
Write:
1. Sales and channel motion comparison
2. Content and campaign footprint
3. GTM edge and gaps for {target_company}
""",
        ),
    ]
)

RECENT_ACTIVITY_COMPARATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            f"""You are a competitive intelligence analyst summarizing recent activity.
Focus on launches, leadership moves, partnerships, acquisitions, and strategic signals.
{_COMPARATOR_RULES}""",
        ),
        (
            "human",
            _COMPARATOR_HUMAN_BLOCK
            + """
Write:
1. Most relevant recent moves by each company
2. What those moves imply strategically
3. Momentum risks/opportunities for {target_company}
""",
        ),
    ]
)


DIMENSION_COMPARATOR_PROMPTS = {
    "product_pricing": PRODUCT_PRICING_COMPARATOR_PROMPT,
    "market_position": MARKET_POSITION_COMPARATOR_PROMPT,
    "traction_growth": TRACTION_GROWTH_COMPARATOR_PROMPT,
    "customer_sentiment": CUSTOMER_SENTIMENT_COMPARATOR_PROMPT,
    "content_gtm": CONTENT_GTM_COMPARATOR_PROMPT,
    "recent_activity": RECENT_ACTIVITY_COMPARATOR_PROMPT,
}


BATTLECARD_SYSTEM = """You are a sales enablement specialist building a competitive battlecard.
Return ONLY valid JSON with no markdown fences and no extra commentary.
Use null for unknown values."""

BATTLECARD_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", BATTLECARD_SYSTEM),
        (
            "human",
            """Build a competitive battlecard for **{target_company}** vs: {competitors}

Research comparisons:
{comparisons_text}

Structured evidence bundle:
{dimension_evidence}

Competitor rationale:
{competitor_rationale_text}

Return JSON matching exactly:
{{
  "target": "{target_company}",
  "competitors": {competitors_json},
  "competitor_profiles": [
    {{
      "name": "<competitor>",
      "rationale": "<why included>",
      "threat_type": "direct_competitor" | "adjacent_threat" | "channel_threat" | "emerging_threat"
    }}
  ],
  "feature_matrix": [
    {{
      "feature": "<capability>",
      "companies": {{
        "<company_name>": "yes" | "partial" | "no" | "unknown"
      }}
    }}
  ],
  "pricing_comparison": [
    {{
      "company": "<name>",
      "model": "<pricing model>",
      "entry_price": "<entry price or null>",
      "enterprise": "<enterprise pricing note or null>"
    }}
  ],
  "win_themes": [
    {{
      "vs_competitor": "<competitor>",
      "theme": "<one-line win theme>",
      "evidence": "<supporting evidence>"
    }}
  ],
  "lose_themes": [
    {{
      "vs_competitor": "<competitor>",
      "theme": "<one-line weakness>",
      "evidence": "<supporting evidence>"
    }}
  ],
  "key_risks": ["<risk>"],
  "confidence_summary": {{
    "<dimension>": "high" | "medium" | "low"
  }},
  "data_gaps": ["<important gap>"],
  "objection_handlers": [
    {{
      "objection": "<objection>",
      "response": "<response>"
    }}
  ]
}}
""",
        ),
    ]
)


_EDITOR_L1 = """You are a senior competitive intelligence analyst at a top-tier strategy consultancy.
Synthesize dimension-level comparisons into a practical executive report.

Non-negotiable rules:
- Ground every claim in provided evidence.
- Begin with market lens and comparison basis before conclusions.
- Mark data gaps and low-confidence claims explicitly.
- Never convert weak evidence into certainty.
- If pricing data is weak, explicitly state "public pricing unavailable" and explain fallback evidence.
- Keep concise professional markdown with clear section structure.
- Use inline citations in the format (Source Name, Month Year) — e.g. (Reuters, Mar 2025). NEVER use bare numeric references like (1), (8), or [3] in the report body.
- End with a ## Sources section listing all cited references as numbered clickable markdown links.
"""

EDITOR_COMPILE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _EDITOR_L1),
        (
            "human",
            """Compile a competitive intelligence report for **{target_company}**.

Report type: {report_type_label}
Research date: {research_date}
Companies: {target_company} vs {competitors}
Output language: {language_instruction}
Market lens: {market_lens}
Comparison basis: {comparison_basis}

Template:
{template}

Research comparisons:
{comparisons_text}

Battlecard data:
{battlecard_summary}

Competitor rationale:
{competitor_profiles_text}

Data gaps and confidence:
{data_gaps_text}

Low-confidence claims:
{low_confidence_text}

Quality flags:
{quality_flags_text}

Source references:
{references_text}

Requirements:
1. Follow the template structure.
2. Use explicit numbers for quantitative claims.
3. Include actionable conclusions with confidence caveats.
4. End with numbered clickable source links.
5. If any dimension is marked "comparison unavailable" in Data gaps, do NOT create a section for it — skip it entirely and do not mention it failed. Number the remaining sections sequentially.
6. Immediately after the Executive Summary, insert a "## Competitive Snapshot" section containing a single markdown table. Columns: Company | Revenue | Growth | Key Strength | Key Risk. Include one row per company (target first, then competitors). Use "N/A" for any unknown value. Keep each cell concise (≤12 words). Do not repeat this table elsewhere in the report.
""",
        ),
    ]
)

EDITOR_EDIT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _EDITOR_L1),
        (
            "human",
            """You are revising an existing competitive intelligence report.

Edit mode: {edit_mode}
Edit instruction: {edit_instruction}
Report type: {report_type_label}
Research date: {research_date}
Companies: {target_company} vs {competitors}
Output language: {language_instruction}
Market lens: {market_lens}
Comparison basis: {comparison_basis}

Current report:
{current_report}

Updated research:
{updated_comparisons}

Competitor rationale:
{competitor_profiles_text}

Data gaps and confidence:
{data_gaps_text}

Low-confidence claims:
{low_confidence_text}

Quality flags:
{quality_flags_text}

Edit mode rules:
- quick_edit: only apply requested textual changes.
- targeted_refresh: refresh only sections with updated evidence.
- full_refresh: rewrite full report using updated evidence.
Return the full revised report.
""",
        ),
    ]
)

