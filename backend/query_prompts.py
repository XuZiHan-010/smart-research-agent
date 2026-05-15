"""Query-generation prompts for market-study theme research.

Critical: queries are sent to Exa's NEURAL semantic search, NOT Google.
Exa does not parse Google search operators — it semantically embeds the
entire query string. Using `site:`, `OR`, `AND`, `""`, or `2021..2031`
syntax will degrade or zero-out results.
"""

from langchain_core.prompts import ChatPromptTemplate

QUERY_FORMAT_GUIDELINES = """
Return ONLY search queries, one per line.
No numbering, no bullets, no extra text, no JSON.
Generate exactly {num_queries} queries.

CRITICAL — query style rules (Exa is a SEMANTIC / NEURAL search engine, NOT Google):
- DO NOT use search operators: no `site:`, no `OR`, no `AND`, no quoted `"..."`, no `inurl:`, no `intitle:`, no `2021..2031` date-range, no `-` exclusion.
- Write natural-language phrases as if you were searching a research database.
- Each query should read like a topic / sentence, not a boolean expression.
- To target authoritative sources, NAME the organization in the query
  (e.g. "国家统计局 / 工信部 / 国家发改委 / 36氪 / IDC / 麦肯锡"),
  not `site:stats.gov.cn`.
- Include concrete terms a report would contain: 数字、年份、机构名、政策名、产品/技术术语。
- Mix Chinese and English queries when useful (about half-half if both
  Chinese and Western sources are likely to have data).
- If research_domain is broad or ambiguous, infer a reasonable sub-focus
  from common market-research practice and make that focus visible.

Good examples:
- 中国低空经济 2024 市场规模 数据 国家统计局
- 工信部 低空经济 产业链 政策 发展规划
- low altitude economy China market size 2024 IDC McKinsey report

Bad examples (DO NOT produce):
- site:stats.gov.cn 低空经济 市场规模 2021..2031
- "low-altitude economy" site:reuters.com OR site:bloomberg.com
"""


THEME_QUERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是市场调研检索专家，要为 Exa 神经语义搜索引擎生成高质量自然语言 query。
每个 query 必须同时考虑研究领域、主题、地理范围和时间范围。
优先用自然语言提到权威来源、行业报告、政策文件、机构名称、关键数据术语。

注意：Exa 不是 Google，不识别 site:/OR/AND/""/2021..2031 等高级搜索操作符——
如果你使用了这些操作符，Exa 会把整串当作语义短语去匹配，导致召回率极低。
请用纯自然语言书写。

{format_guidelines}"""),
    ("human", """研究领域：{research_domain}
主题：{theme_label_zh}
地理范围：{geography_labels}
时间范围：{time_start} 到 {time_end}
可参考的权威机构与媒体（请把它们的中文/英文机构名直接写进自然语言查询，不要用 site:）：
{authoritative_domains}

生成检索 query，每行一条，纯自然语言，不要使用 site:/OR/""/.. 等任何操作符。"""),
])
