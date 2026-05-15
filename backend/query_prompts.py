"""Query-generation prompts for market-study theme research."""

from langchain_core.prompts import ChatPromptTemplate

QUERY_FORMAT_GUIDELINES = """
Return ONLY search queries, one per line.
No numbering, no bullets, no extra text.
Generate exactly {num_queries} queries.
Mix Chinese and English queries when useful.
If research_domain is broad or ambiguous, infer a reasonable sub-focus from
common market-research practice and make that focus visible in the queries.
"""


THEME_QUERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是市场调研检索专家，要为 Exa 生成高质量搜索 query。
每个 query 必须同时考虑研究领域、主题、地理范围和时间范围。
优先覆盖权威来源、行业报告、政策文件、新闻与机构数据。
{format_guidelines}"""),
    ("human", """研究领域：{research_domain}
主题：{theme_label_zh}
地理范围：{geography_labels}
时间范围：{time_start} 到 {time_end}
权威域名参考：{authoritative_domains}

生成检索 query。"""),
])
