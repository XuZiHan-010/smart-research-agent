"""
Query-generation prompts for the 6 competitor research dimensions.
Each prompt is a ChatPromptTemplate used by the corresponding researcher to
ask GPT-4.1-mini to generate targeted Exa search queries.

Variables available in every prompt:
  {company}          — company name being researched
  {num_queries}      — how many queries to generate (from depth config)
  {format_guidelines}— standard output format instruction
  {grounding_context}— optional official website excerpt (first 2000 chars)
"""

from langchain_core.prompts import ChatPromptTemplate

# ── Shared format instruction ──────────────────────────────────────────────────

QUERY_FORMAT_GUIDELINES = """
Return ONLY the search queries, one per line.
No numbering, no bullets, no extra text.
Generate exactly {num_queries} queries.
Each query must be specific, diverse, and optimised for finding factual information.
"""

# ── Per-dimension query prompts ────────────────────────────────────────────────

PRODUCT_PRICING_QUERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a product intelligence researcher generating precise web-search queries.
Focus on how this company monetises and what distinguishes its offering. Infer the
company type from {grounding_context} and surface whichever signals apply:
  - SaaS / software: feature matrix, pricing tiers, free vs paid plans,
    per-seat vs usage-based pricing, enterprise pricing, API access, integrations
  - B2B industrial / chemicals / materials / hardware: product catalog,
    technical datasheets, SKUs, application areas, safety data sheets,
    distributor pricelists, quote-based enterprise pricing, certifications
  - Consumer brand / retail / CPG: product lines, RRP, retail channels,
    pack sizes, private label vs flagship, promotional pricing, shelf placement
Choose the category that best matches the company and generate queries targeted
at sources that actually publish those signals (avoid forcing SaaS terms on
industrial firms or vice versa).
{format_guidelines}"""),
    ("human", """Generate search queries to research the product and pricing of: {company}
{grounding_context}"""),
])

MARKET_POSITION_QUERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a market intelligence researcher generating precise web-search queries.
Focus: market positioning, target customer segments, brand perception, industry analyst
rankings (Gartner Magic Quadrant, Forrester Wave, IDC MarketScape),
market share estimates, ICP (ideal customer profile), competitive differentiation.
{format_guidelines}"""),
    ("human", """Generate search queries to research the market position of: {company}
{grounding_context}"""),
])

TRACTION_GROWTH_QUERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a growth analyst generating precise web-search queries.
Focus on any evidence of business scale and momentum. Depending on the company type,
relevant signals may include:
  - Startups: funding rounds, valuation, ARR, user count, runway
  - Public / mature enterprises: annual revenue, segment growth, market share,
    employee headcount, geographic expansion, M&A activity, earnings reports
  - Private / family-owned: revenue estimates, headcount, IR disclosures, press coverage
Generate queries that would surface whichever signals exist for this specific company.
{format_guidelines}"""),
    ("human", """Generate search queries to research the business traction and growth of: {company}
{grounding_context}"""),
])

CUSTOMER_SENTIMENT_QUERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a customer research analyst generating precise web-search queries.
Infer the company type from {grounding_context} and target the review channels
where its customers actually leave feedback:
  - SaaS / software: reviews on G2, Capterra, Trustpilot, TrustRadius,
    Reddit software subs, NPS scores, churn reasons, switching stories
  - B2B industrial / chemicals / materials / hardware: LinkedIn customer
    case studies, testimonials on distributor sites, supplier scorecards,
    industry forum threads, Reddit industry subs, procurement reviews,
    technical support feedback
  - Consumer brand / retail / CPG: Amazon and retailer reviews, social media
    sentiment, consumer complaint boards, product quality discussions,
    unboxing/haul content
Do not force SaaS review sites onto companies whose customers are other
manufacturers or end consumers.
{format_guidelines}"""),
    ("human", """Generate search queries to research customer sentiment about: {company}
{grounding_context}"""),
])

CONTENT_GTM_QUERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a go-to-market researcher generating precise web-search queries.
Infer the company type from {grounding_context} and generate queries for the
GTM motions that actually apply:
  - SaaS / software: content marketing, SEO footprint, blog/podcast/YouTube,
    sales motion (PLG vs sales-led), pricing page strategy, affiliate programmes,
    community-led growth, demand generation tactics
  - B2B industrial / chemicals / materials / hardware: trade shows and industry
    events, technical whitepapers and application notes, distributor and
    channel partner networks, industry certifications (ISO, UL, REACH),
    corporate case studies, field sales force, technical support content
  - Consumer brand / retail / CPG: retail partnerships and shelf strategy,
    DTC e-commerce, influencer marketing, social/TikTok campaigns,
    loyalty programmes, in-store activation, brand storytelling
{format_guidelines}"""),
    ("human", """Generate search queries to research the content and GTM strategy of: {company}
{grounding_context}"""),
])

RECENT_ACTIVITY_QUERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a news researcher generating precise web-search queries.
Focus: product launches, feature releases, funding announcements, M&A activity,
executive changes, strategic partnerships, awards, controversies, or pivots
in the LAST 6 MONTHS. Prefer recent primary sources.
{format_guidelines}"""),
    ("human", """Generate search queries for the latest news and activity about: {company}
{grounding_context}"""),
])

# ── Dimension → prompt mapping (used by research_dispatcher) ──────────────────

DIMENSION_QUERY_PROMPTS = {
    "product_pricing":    PRODUCT_PRICING_QUERY_PROMPT,
    "market_position":    MARKET_POSITION_QUERY_PROMPT,
    "traction_growth":    TRACTION_GROWTH_QUERY_PROMPT,
    "customer_sentiment": CUSTOMER_SENTIMENT_QUERY_PROMPT,
    "content_gtm":        CONTENT_GTM_QUERY_PROMPT,
    "recent_activity":    RECENT_ACTIVITY_QUERY_PROMPT,
}
