# Smart Research Agent 架构优化 Prompt

> 将以下内容完整发送给 Claude Opus，作为一次性上下文。

---

## 角色设定

你是一位资深 AI 应用架构师，专精于 LLM 应用的性能优化、成本控制和架构设计。我需要你帮我全面优化一个竞品研究 Agent 的架构。

---

## 项目概述

Smart Research Agent 是一个 AI 驱动的竞品研究平台，用户输入公司名称后，系统自动从 6 个维度搜集、分析、合成信息，最终生成专业研究报告。

**技术栈：**
- 后端：FastAPI + LangGraph（状态图编排）
- 前端：React + TypeScript + Vite
- 数据库：MongoDB（任务历史持久化）
- 搜索：Exa API（neural search + 全文抓取）
- LLM：
  - OpenAI GPT-4.1-mini → 搜索查询生成（6个维度各1次调用）
  - Google Gemini 2.5 Flash → 维度简报合成（6个维度并行，semaphore=3）
  - OpenAI GPT-4.1 → 最终报告编排（1次调用，streaming）

---

## 当前架构与完整数据流

```
用户输入 (company, dimensions[], depth, format, template?)
    ↓
[Planner] — 确定性配置，无LLM调用
    ↓         生成 research_plan: { active_dimensions, queries_per_dimension, results_per_query }
    ↓         depth 配置: quick(2查询×3结果) | standard(4×5) | deep(6×8)
[Grounding] — Exa 抓取公司官网（max 8000 chars），作为后续所有研究的锚点
    ↓
[6 Researchers 并行] — 每个维度独立执行：
    │  1. LLM (GPT-4.1-mini) 生成搜索查询（基于维度 prompt + 官网摘要前2000字）
    │  2. Exa neural search 并行执行所有查询
    │  3. 按 URL 去重，保留最高 score
    │  搜索策略按维度不同：
    │    - company_overview: category="company"
    │    - team_and_size:    category="people" + category="company"
    │    - financial:        限定域名 (crunchbase, pitchbook, bloomberg, reuters, wsj, 36kr, sina)
    │    - news:             category="news" + 6个月时间过滤
    │    - competition:      category="company" + 限定域名 (Gartner, Forrester, McKinsey, BCG, HBR)
    │    - industry:         限定域名 (Statista, IBISWorld, MordorIntelligence, GrandView, McKinsey)
    ↓  (fan-in via merge_dicts reducer on dimension_data)
[Collector] — 日志汇总，pass-through
    ↓
[Curator] — 过滤 + 富化：
    │  1. 按 Exa score >= 0.3 过滤
    │  2. 每维度最多保留 15 篇
    │  3. Exa get_contents() 批量获取全文（batch=20, 每篇 max 4000 chars）
    │  4. 构建 references 列表（按 score 排序, 域名去重, max 10条）
    ↓
[Briefing] — Gemini 2.5 Flash 按维度合成简报：
    │  - 每维度最多 20 篇文档，总 context cap 80,000 chars
    │  - 6 个专门的 briefing prompt（每个 300-600 words 目标）
    │  - 共享 BRIEFING_SYSTEM prompt（通用指令约 200 tokens）
    │  - 3 个并发 semaphore 限制
    ↓
[Editor] — GPT-4.1 编排最终报告：
    │  - 输入：所有 briefings 拼合 + references 列表
    │  - 支持默认格式和用户自定义 template 两种模式
    │  - Streaming 输出到前端
    ↓
[OutputFormatter] — markdown(pass-through) | PDF(ReportLab) | JSON(结构化提取)
    ↓
[MongoDB 持久化] + [SSE 实时推送到前端]
```

---

## 核心代码结构

```
smart-research-agent/
├── api.py                    # FastAPI 服务入口，REST + SSE + 静态文件
├── backend/
│   ├── graph.py              # LangGraph StateGraph 定义，编排整个流水线
│   ├── prompts.py            # 所有 LLM prompt 集中管理（查询/简报/编辑/JSON格式化）
│   ├── classes/
│   │   └── state.py          # ResearchState TypedDict，含 merge_dicts reducer
│   ├── nodes/
│   │   ├── planner.py        # 确定性配置（无LLM）
│   │   ├── grounding.py      # Exa 官网抓取
│   │   ├── collector.py      # fan-in 日志汇总
│   │   ├── curator.py        # 过滤(score)、富化(全文)、references构建
│   │   ├── briefing.py       # Gemini 2.5 Flash 维度合成
│   │   ├── editor.py         # GPT-4.1 报告编排（streaming）
│   │   ├── output_formatter.py  # markdown/PDF/JSON 输出
│   │   └── researchers/
│   │       ├── base.py       # BaseResearcher 抽象基类
│   │       ├── company.py    # CompanyResearcher (EXA_SEARCH_CONFIGS 定义搜索策略)
│   │       ├── team.py       # TeamResearcher
│   │       ├── financial.py  # FinancialResearcher（限定金融域名）
│   │       ├── news.py       # NewsResearcher（时间过滤）
│   │       ├── competition.py # CompetitionResearcher（两阶段搜索）
│   │       └── industry.py   # IndustryResearcher（限定行业研究域名）
│   └── services/
│       ├── mongodb_service.py
│       └── pdf_service.py
└── frontend/                 # React + Vite + TypeScript
```

---

## Prompt 结构详情

### 查询生成 Prompt（6个变体，结构一致）
```python
# System prompt（所有维度共享前缀）
"You are a business intelligence researcher generating precise web-search queries."
# 然后每个维度有不同的 Focus 行：
# company_overview: "Focus: company fundamentals — products/services, history, leadership, business model, mission."
# financial:        "Focus: funding rounds, valuations, revenue, investors, financial performance, IPO status."
# ...以此类推

# Human prompt
"Generate search queries to research the company: {company}"
# 附加 grounding_context（官网前2000字）
```

### 简报合成 Prompt（6个变体，共享 BRIEFING_SYSTEM）
```python
BRIEFING_SYSTEM = """You are a senior business analyst writing a structured research briefing.
Write in clear, professional prose. Be factual and cite specific details from the sources.
Do NOT invent information. If data is missing, say so briefly.
Format: use markdown headers (##, ###) and bullet points where helpful.
Length: comprehensive but concise — aim for 300-600 words."""

# 每个维度的 Human prompt 结构：
"Write a {维度名称} briefing for **{company}** using the research below.
Cover:
- {维度特定的要点列表}

Research:
{context}"  # context = 最多20篇文档，每篇格式为 "### [title](url) (relevance: score)\n{content}"
```

### 编辑/编排 Prompt
```python
EDITOR_SYSTEM = """You are a senior research editor at a top-tier consulting firm.
Your job is to assemble individual research briefings into a single, polished, executive-level report.
Rules:
- Maintain all factual content; do NOT add information that wasn't in the briefings.
- Remove exact duplicates and smooth redundant phrasing across sections.
- Use clean, professional markdown.
- Write a short executive summary (3-5 sentences) at the top.
- Preserve all dimension sections the researcher provided."""

# Human prompt：将所有 briefings 拼合 + references 列表传入
```

---

## 当前 LLM 调用量分析（以 standard depth, 6 维度为例）

| 阶段 | 模型 | 调用次数 | 输入规模(估算) | 说明 |
|------|------|---------|--------------|------|
| 查询生成 | GPT-4.1-mini | 6次 | 每次 ~500 tokens | 系统prompt + 官网摘要 + 公司名 |
| 简报合成 | Gemini 2.5 Flash | 6次 | 每次 ~20K-80K chars | 共享系统prompt + 维度prompt + 文档context |
| 报告编排 | GPT-4.1 | 1次 | ~5K-15K chars | 所有briefings拼合 |
| **总计** | | **13次** | | |

---

## 已研究的技术方向

### 1. Prompt Caching（来自 Anthropic 文档）
- 缓存 prompt 前缀，后续相同前缀的请求直接读取缓存
- 缓存读取成本仅为正常输入的 1/10（以 Claude 为例）
- 默认 5 分钟 TTL，可选 1 小时
- **在我们项目的潜在应用点：**
  - Briefing 阶段 6 次调用共享 BRIEFING_SYSTEM prompt
  - 同一公司多次研究时复用文档上下文
  - 批量竞品分析时共享行业背景
  - 注意：OpenAI 和 Gemini 也有类似的原生缓存机制可利用

### 2. Contextual Retrieval（来自 Anthropic 工程博客）
- 在文档分块前，用 LLM 为每个块生成上下文说明（50-100 tokens）
- Contextual Embeddings + Contextual BM25 混合检索，失败率降低 67%
- 配合 Prompt Caching 可将成本控制在每百万 token $1.02
- **我们的结论：当前架构不需要知识库**
  - 竞品研究的核心诉求是"新"不是"全"，信息有强时效性
  - 现有的"搜索→合成"单次流水线是正确模式
  - 知识库维护成本（时效管理、去重、嵌入）投入产出比不高
  - **更有价值的方向：**基于已有 MongoDB 历史报告做报告对比和趋势追踪

---

## 已识别的问题与优化机会

### 成本与效率
1. **Briefing 阶段是成本大头** — 6次 Gemini 调用，每次高达 80K chars 上下文，但共享的 BRIEFING_SYSTEM 每次都重复发送
2. **查询生成可能过于简单** — 仅基于公司名 + 维度关键词，没有利用已获取的信息做迭代优化
3. **Curator 的过滤策略粗糙** — 仅用 Exa score >= 0.3 单一阈值，没有内容质量评估

### 报告质量
4. **搜索结果质量不稳定** — 对于小公司或非英文公司，Exa 搜索可能返回不相关结果
5. **Briefing 和 Editor 之间可能存在信息损失** — Briefing 合成后 Editor 无法回溯原始文档
6. **缺少事实核验机制** — 没有交叉验证不同来源的信息一致性

### 架构扩展性
7. **单次执行模式** — 每次研究都从零开始，无法利用历史研究加速
8. **维度之间没有信息共享** — 例如 competition 维度发现的竞品名单没有反馈给 industry 维度
9. **没有错误重试机制** — 单个 Exa 搜索或 LLM 调用失败会导致该维度数据缺失

### 产品功能
10. **缺少报告历史对比** — MongoDB 存了历史但无法做"上次 vs 这次"对比
11. **缺少趋势追踪** — 无法回答"这家公司过去6个月的变化"
12. **没有批量竞品分析** — 用户无法一次研究多家竞品并生成对比矩阵

---

## 你需要做的

请基于以上完整的项目上下文，给出**分层次的架构优化方案**。要求：

### 第一层：立即可做的优化（不改变整体架构，1-2天工作量）
- 现有 LLM 调用的成本优化（缓存策略、模型选择、prompt 精简）
- Curator 过滤和排序策略改进
- 错误处理和重试机制
- 搜索查询质量提升

### 第二层：中期架构改进（需要一定重构，1-2周工作量）
- 维度间信息共享机制
- Briefing 质量提升方案
- 报告历史对比和趋势追踪功能
- 批量竞品分析支持

### 第三层：长期演进方向（可选，需要产品层面决策）
- 是否以及何时引入 RAG/知识库
- 多数据源集成策略
- 用户反馈循环和报告质量迭代
- 企业级功能（多用户、权限、定时监控）

### 输出要求
1. 每个优化建议都要有**具体的实现方案**（涉及到哪个文件、怎么改、代码示例）
2. 标注每个优化的**预期收益**（成本节省百分比、延迟减少、质量提升）
3. 标注**实现复杂度**和**风险点**
4. 如果涉及模型切换（比如某个环节换成 Claude），要给出**详细的利弊分析**
5. 优化方案之间如果有依赖关系，明确标注执行顺序

请开始你的分析。
