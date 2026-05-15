# Smart Research Agent → Market Study Agent  PRD

> 本文档为项目最终 PRD，作为开发执行的唯一依据。
> - 需求源：`V5 Prompt.txt`（汉高市场部中文市场调研报告）
> - 架构指导：Anthropic 三篇 Agent 工程文章（Building Effective Agents / Effective Harnesses / Context Engineering）
> - 交付模式：**vibe coding**，一次性交付**完整基础版本**，不拆 Phase 节奏

---

## 0. Context（为什么做这件事）

当前 [smart-research-agent](.) 是 SaaS **竞品分析**系统（N 公司 × 6 维度）。真实业务需求是为汉高市场部生成**中文市场调研报告**——研究对象从"N 个公司"换成"1 个市场领域"，输入字段、Schema、对话流、输出形式全部要改造。

**目标**：把项目重构为 **Market Study Agent**——输入 1 个研究领域，经"输入助手 → 范围确认问卷 → 多主题并行深研 → 跨主题校验 → 中文报告"全自动产出符合 V5 Prompt 要求的报告（含溯源、Word/PDF/MD 三格式）。

**与原项目的关系**：保留 LangGraph / Exa / MongoDB / SSE / PDF / Editor 流式等全部底层基础设施，按 Anthropic 原则系统性应用 Workflow + Orchestrator-Workers + Context Isolation。

**关键决策（PRD 锁定，不再讨论）**：
- 🔴 **彻底废弃 competitor 模式**：删除 `/discover`、`/start` 旧路径，删除 DiscoveryPanel、competitor 相关 researchers 与 prompts。无双轨。
- 🔴 **自定义主题保留**：用户在 7 个默认主题基础上可新增**最多 3 个**自定义主题（仅输入名称），走通用 sub-agent prompt。
- 🔴 **基础版本必含**：两轮对话、ThemeSubAgent 并发、cross_validator、9 章节中文报告、Citation 内联+末尾清单、Word/PDF/MD 输出、Agent Traces、Checkpointing。
- 🟡 **基础版本尽力而为（不硬卡）**：每章节 ≥1 表格、历史/预测段落区分。Editor prompt 强写要求，但不阻塞交付。

---

## 1. 用户与使用场景

### 1.1 目标用户
- 汉高市场部分析师（中文）。
- 简历/赛题评审人（英文阅读，看架构与代码组织）。

### 1.2 核心用户故事
1. 分析师在 Sidebar 输入"中国新能源汽车动力电池市场"，点击 Start。
2. 输入助手判定无歧义 → 自动进入 Round 1 问卷；若有歧义（如"新能源电池"）→ 弹出 2-4 个澄清选项，用户选定后再进。
3. 问卷面板：勾选 7 个默认主题（默认全选）+ 可新增 ≤3 个自定义主题；选地理（默认中国大陆）；选时间窗（默认今天 ± 5 年）。
4. 点 Confirm → 后端启动 LangGraph job，前端 SSE 实时展示各 sub-agent 进度。
5. 报告生成完毕 → 中文 Markdown 渲染 + `[N]` 内联引用 + 末尾参考清单 + 下载按钮（md/pdf/word）。
6. 用户可在 "Agent Decisions" 抽屉查看每个 LLM 调用的轨迹（用于调试与赛题展示）。

---

## 2. 范围（Scope）

### 2.1 In Scope（基础版本必含）
| 模块 | 要求 |
|---|---|
| 输入助手 | LLM 流式判定 + 歧义打断 + 选项给出 |
| Round 1 问卷 | 7 默认主题（全选） + ≤3 自定义主题 + 多选地理（默认 cn） + 时间窗（默认 today±5y） |
| Round 2 执行 | LangGraph 子图：theme_orchestrator → 多 ThemeSubAgent 并发 → cross_validator → compactor → editor → output_formatter |
| 中文报告 | V5 Prompt 9 章节顺序；未勾选主题章节直接跳过、编号顺延；末尾"关键来源清单" |
| Citation | sub-agent 内强制 `[cite:doc_id]` → citation_service 解析为 `[N]` + 末尾参考表 |
| 输出格式 | md / pdf / word 三格式下载；PDF/Word 中文字体；表格保持原生格式（非图片） |
| Agent Traces | 每次 LLM 调用记录到 MongoDB `agent_traces` 集合；提供 `/traces` API + 前端抽屉 |
| Checkpointing | sub-agent 完成立即写 MongoDB；提供 `/resume` API |
| Cross Validator | LLM 节点检查跨主题冲突、引用、信息缺口；触发 retry 或加 quality_flag |

### 2.2 Best-Effort（Editor prompt 强写但不硬卡交付）
- 每章节至少 1 个 Markdown 表格（由 sub-agent 直接输出，不引入独立 table_assembler 节点）。
- 预测主题区分历史/预测段落（以 today 为界），并标注假设/来源/不确定性。

### 2.3 Out of Scope（v2+）
- competitor 双轨保留（**彻底删除**）。
- 自定义主题 schema 生成、LLM 辅助主题建议。
- 报告多轮编辑、行业模板库、RAG 接入。
- 多语言切换（硬中文）。

---

## 3. 功能需求

### 3.1 输入与对话流
| 字段 | 说明 |
|---|---|
| `researchDomain` | 单一研究领域文本，必填，单行 |
| `depth` | snapshot / standard / deep_dive，保留现有 enum |
| `outputFormat` | markdown / pdf / word（新增 word） |

提交 Start 后**不直接 start job**，先调输入助手。

### 3.2 输入助手（Round 0）
- 端点：`POST /api/research/validate_domain`（SSE 流式）
- 单次 GPT-4.1-mini structured output，prompt：
  > 你是市场研究助手。判断用户输入的研究领域是否清晰无歧义。
  > 1. 含行业 + 地理 + 产品/服务范围 → confirmed=true
  > 2. 错别字、缩写、多义、过宽、过窄 → confirmed=false + 2-4 个选项
  > 3. 给出"我理解为 XXX"陈述供用户确认
- 输出：`{ confirmed, understood_as, ambiguities?: [{option, recommended, why}], message }`
- 字符级 token 流通过 SSE 推送 `message`。

### 3.3 Round 1 问卷
- 端点：`POST /api/research/clarify`
- 返回：
  ```json
  {
    "clarification_id": "uuid",
    "research_domain": "中国新能源汽车动力电池",
    "themes": [{"key": "market_size", "label_zh": "市场规模与增长趋势", "checked": true}, ...×7],
    "custom_themes_max": 3,
    "geography_options": [
      {"key": "cn", "label_zh": "中国大陆", "checked": true},
      {"key": "us", "label_zh": "美国", "checked": false},
      {"key": "eu", "label_zh": "欧盟", "checked": false},
      {"key": "jp", "label_zh": "日本", "checked": false},
      {"key": "kr", "label_zh": "韩国", "checked": false},
      {"key": "in", "label_zh": "印度", "checked": false},
      {"key": "sea", "label_zh": "东南亚", "checked": false},
      {"key": "global", "label_zh": "全球", "checked": false}
    ],
    "time_range": {"start": "YYYY-MM (today-5y)", "end": "YYYY-MM (today+5y)", "today": "YYYY-MM"}
  }
  ```
- 暂存于 MongoDB `clarifications` 集合（24h TTL）。

### 3.4 7 个默认主题（固定 key）
1. `market_size` 市场规模与增长趋势
2. `industry_chain` 产业链分析
3. `products_applications` 主要产品、服务与应用场景
4. `competitive_landscape` 竞争格局
5. `policy` 政策与监管环境
6. `tech_trend` 技术趋势
7. `investment` 投融资、并购与战略合作动态

### 3.5 自定义主题
- 用户在问卷中可点 [+ 添加主题] 输入名称，**最多 3 个**。
- 前端约束：单个名称 2-30 字符；不能与 7 个默认主题重名（按 label_zh 校验）。
- 后端：与默认主题走相同 ThemeSubAgent 类，但使用**通用 prompt 模板** + 无 schema 表格约束（表格由 LLM 自行决定结构）。
- 报告中自定义主题排在 7 个固定章节之后、参考清单之前，按用户输入顺序编号。

### 3.6 Round 2 启动
- 端点：`POST /api/research/confirm`
- 入参：
  ```json
  {
    "clarification_id": "...",
    "selected_themes": ["market_size", "industry_chain", ...],
    "custom_themes": ["ESG与可持续", "海外出海动态"],
    "geography": ["cn", "us"],
    "time_range": {"start": "2021-05", "end": "2031-05"},
    "depth": "standard",
    "output_format": "word"
  }
  ```
- 校验：≥1 默认/自定义主题；≥1 地理；start < end；自定义主题 ≤3。
- 出参：`{ job_id }`，前端走 `/stream` SSE。

### 3.7 报告章节顺序
```
# {{研究领域}} 市场调研报告
## 1. 市场规模与增长趋势       (若 selected)
## 2. 产业链分析               (若 selected)
## 3. 主要产品、服务与应用场景  (若 selected)
## 4. 竞争格局                 (若 selected)
## 5. 政策与监管环境           (若 selected)
## 6. 技术趋势                 (若 selected)
## 7. 投融资、并购与战略合作动态 (若 selected)
## 8+. {{自定义主题 1..3}}     (按用户输入顺序)
## 关键来源清单                (始终输出，编号顺延)
```
未勾选主题**直接跳过不留占位**，编号按勾选后实际顺序连续。

---

## 4. 系统架构

### 4.1 范式选择
报告章节固定、流程可预测 → **Workflow**（不是 ReAct Agent）。Anthropic 建议 "start with workflows, only add agentic loops when truly needed"——本场景属于前者。

### 4.2 Anthropic 模式映射
| Pattern | 对应需求 | 落地节点 |
|---|---|---|
| Prompt Chaining | 输入助手 → 范围确认 → 执行 | validate_domain → clarify → confirm → graph |
| Routing | 单一 mode（market_study），保留 router 节点便于未来扩展 | router |
| Parallelization | 多主题独立、互不依赖 | theme_orchestrator + asyncio.gather + Semaphore |
| Orchestrator-Workers | 每主题独立深度研究 | theme_orchestrator → N 个 ThemeSubAgent |
| Evaluator-Optimizer | 跨主题校验 + 信息缺口标注 | cross_validator 节点 |

### 4.3 Harness 原则落地
- **Tool result compaction**：Exa 原文进 LLM 前必经截断/摘要
- **Checkpointing**：sub-agent 完成立即写 MongoDB；崩溃后从最后完成主题续跑
- **Observability**：每次 LLM 调用记录到 `agent_traces` 集合
- **Recovery**：单 sub-agent 失败不拖累其他

### 4.4 Context Engineering 原则
- **Sub-agents for context isolation**：每主题独立 LLM context window
- **Structured note-taking**：sub-agent 返回 `ThemeReport`（不返回原始对话）
- **Just-in-time loading**：沿用现有 curator 按需 `get_contents`
- **Compaction**：进 editor 前把 ThemeReport 压缩为骨架

### 4.5 端到端流程
```
┌─ Frontend ──────────────────────────────────────────────────────┐
│ Sidebar:                                                         │
│   [研究领域 _______]   [深度 ▾]   [输出 ▾]   [Start]              │
│      ↓                                                           │
│ InputAssistant (SSE 流式对话):                                    │
│   POST /api/research/validate_domain                             │
│     ├─ confirmed=true  → 自动进入 Round 1                         │
│     └─ confirmed=false → 渲染歧义选项 → 用户选 → 再次 validate     │
│      ↓                                                           │
│ ClarificationPanel (弹框):                                        │
│   POST /api/research/clarify → 问卷                              │
│     ☑ 7 默认主题（全选）                                          │
│     [+ 添加自定义主题] (≤3)                                       │
│     地理：☑中国大陆 ☐... (≥1)                                     │
│     时间：[start] [end]                                          │
│   [Confirm] → POST /api/research/confirm → job_id                │
│      ↓                                                           │
│ ProgressTracker (SSE 实时):                                       │
│   sub_agent_progress / cross_validation / editor_stream / done   │
│      ↓                                                           │
│ ReportViewer:                                                    │
│   中文 Markdown + [N] hover/click 来源卡 + 下载 md/pdf/word       │
│ TracesDrawer:                                                    │
│   GET /api/research/{id}/traces → Agent 决策时序                  │
└──────────────────────────────────────────────────────────────────┘
```

### 4.6 后端 LangGraph 拓扑
```
router (单分支 → market_study)
  │
  ↓
theme_orchestrator
  │ (按 selected_themes + custom_themes 派发，独立 context)
  ↓ asyncio.gather + Semaphore
┌────────┬────────┬────────┬──────────┐
↓        ↓        ↓        ↓
theme_1  theme_2  ...     custom_theme_X
SubAgent SubAgent          SubAgent
(每 SubAgent 内部:
  query 生成 → Exa 搜索 → 评分 → 按需 get_contents
  → 内部 LLM 生成 ThemeReport{narrative+tables+citations+gaps+forecast}
  → 完成即写 MongoDB checkpoint)
  │ fan-in (operator.add)
  ↓
cross_validator    (LLM 跨主题审查 + 信息缺口标注 + 可触发 retry)
  │
  ↓
compactor          (压缩 ThemeReports → editor 骨架)
  │
  ↓
editor             (按 V5 章节顺序中文组装 + 保留 [cite:doc_id])
  │
  ↓
citation_resolver  ([cite:doc_id] → [N] + 末尾参考表)
  │
  ↓
output_formatter   (md / pdf / word)
```

### 4.7 API 端点
| 方法 | 端点 | 用途 | 状态 |
|---|---|---|---|
| POST | `/api/research/validate_domain` | 输入助手 SSE 流式判定 | **新增** |
| POST | `/api/research/clarify` | 生成 Round 1 问卷 | **新增** |
| POST | `/api/research/confirm` | 启动 Round 2，返回 job_id | **新增** |
| GET | `/api/research/{id}/stream` | SSE 实时事件 | 改造（事件 schema 调整） |
| GET | `/api/research/{id}/report` | 获取完整报告 | 复用 |
| GET | `/api/research/{id}/download?format=md\|pdf\|word` | 下载 | **扩展（新增 word）** |
| GET | `/api/research/{id}/traces` | Agent 决策轨迹 | **新增** |
| POST | `/api/research/{id}/resume` | 从最后 checkpoint 续跑 | **新增** |
| GET | `/api/research/history` | 历史记录 | 复用 |
| DELETE | `/api/research/{id}` | 删除记录 | 复用 |
| GET | `/api/health` | 健康检查 | 复用 |
| ~~POST `/api/research/discover`~~ | ~~~~ | ~~~~ | **删除** |
| ~~POST `/api/research/start`~~ | ~~~~ | ~~~~ | **删除** |
| ~~POST `/api/research/{id}/edit`~~ | ~~~~ | ~~~~ | **删除（v2 再做）** |
| ~~GET `/api/research/{id}/battlecard`~~ | ~~~~ | ~~~~ | **删除** |

---

## 5. 数据模型

### 5.1 State 改造（[backend/classes/state.py](backend/classes/state.py)）
```python
# 删除 CompetitorResearchState 中的 competitor 字段
# 新结构（单一 mode）:
class ResearchState(TypedDict):
    job_id: str
    research_domain: str
    selected_themes: List[str]           # 7 个 key 中勾选的
    custom_themes: List[str]             # ≤3，用户输入名称
    geography: List[str]                 # ≥1，国家/地区 key
    time_range: Dict[str, str]           # {start, end, today}
    depth: Literal["snapshot","standard","deep_dive"]
    output_format: Literal["markdown","pdf","word"]
    theme_reports: Annotated[List[ThemeReport], operator.add]
    validation_report: Optional[Dict]
    compacted_skeleton: Optional[Dict]
    final_report_md: Optional[str]
    citations_map: Optional[Dict]
    events: Annotated[List[Dict], operator.add]
```

### 5.2 ThemeReport 结构
```python
{
  "theme_key": str,            # 默认主题 key 或 "custom_<index>"
  "theme_label_zh": str,
  "is_custom": bool,
  "narrative": str,            # 含 [cite:doc_id] 内联引用
  "tables": List[StructuredTable],     # Markdown 表格 + 元数据
  "citations": Dict[str, Citation],
  "confidence": Literal["high","medium","low"],
  "data_gaps": List[str],
  "forecast_section": Optional[ForecastSection]   # 仅市场规模/技术趋势
}
```

### 5.3 MongoDB 集合
| 集合 | 用途 | 状态 |
|---|---|---|
| `research_jobs` | 任务主表（job 元数据 + 最终报告） | 改造（去 competitor 字段） |
| `curated_refs` | curator 的 doc 全文引用 | 复用 |
| `clarifications` | Round 1 问卷暂存，24h TTL | **新增** |
| `agent_traces` | LLM 调用轨迹 | **新增** |
| `checkpoints` | sub-agent 完成 checkpoint | **新增** |

---

## 6. 前端改造

### 6.1 删除
- [DiscoveryPanel.tsx](frontend/src/components/DiscoveryPanel.tsx)（整文件）
- Sidebar 中 target_company / target_website / competitorNames / report_type / language / template 字段
- ReportEditModal 等 edit 相关组件（v2 再做）

### 6.2 新增/重构
| 文件 | 改动 |
|---|---|
| [Sidebar.tsx](frontend/src/components/Sidebar.tsx) | 仅保留 `researchDomain` + `depth` + `outputFormat`，Start 按钮触发 validate |
| [InputAssistant.tsx](frontend/src/components/InputAssistant.tsx) | **新增**：SSE 对话区，渲染助手回复 + 歧义选项 |
| [ClarificationPanel.tsx](frontend/src/components/ClarificationPanel.tsx) | **新增**：主题勾选 + 自定义主题（≤3） + 地理多选 + 时间窗 |
| [ReportViewer.tsx](frontend/src/components/ReportViewer.tsx) | `[N]` hover/click 来源卡 + word 下载按钮 |
| [TracesDrawer.tsx](frontend/src/components/TracesDrawer.tsx) | **新增**：调用 `/traces`，时序展示 LLM 调用 |
| [useResearch.ts](frontend/src/hooks/useResearch.ts) | phase: `idle → validating → ambiguous? → clarifying → confirming_scope → running → completed` |
| [types/index.ts](frontend/src/types/index.ts) | 全量更新类型；删除 competitor 类型；新增 ThemeReport/Citation 等 |

---

## 7. 后端改造

### 7.1 删除
- [backend/nodes/researchers/](backend/nodes/researchers/) 下所有 competitor 维度 researcher
- [backend/nodes/comparator.py](backend/nodes/comparator.py)
- [backend/nodes/battlecard_builder.py](backend/nodes/battlecard_builder.py)
- [backend/services/discovery_service.py](backend/services/discovery_service.py)
- 对应 prompts（comparator / battlecard / 旧 editor）
- competitor 相关 evals

### 7.2 新增
| 路径 | 用途 |
|---|---|
| [backend/classes/market_study_config.py](backend/classes/market_study_config.py) | `MARKET_THEMES`、`THEME_LABELS_ZH`、`THEME_TABLE_SCHEMAS`、`AUTHORITATIVE_DOMAINS_BY_THEME`、`GEOGRAPHY_OPTIONS` |
| [backend/services/domain_validator_service.py](backend/services/domain_validator_service.py) | `validate_domain()` SSE 流式 |
| [backend/services/clarification_service.py](backend/services/clarification_service.py) | `build_questionnaire()` + clarifications 集合读写 |
| [backend/services/citation_service.py](backend/services/citation_service.py) | `assign_doc_ids()` / `resolve_citations()` |
| [backend/services/trace_service.py](backend/services/trace_service.py) | LLM 调用 trace 记录与查询 |
| [backend/nodes/sub_agents/theme_sub_agent.py](backend/nodes/sub_agents/theme_sub_agent.py) | 基类（含 7 个默认主题 + 通用自定义 prompt 分支） |
| [backend/nodes/theme_orchestrator.py](backend/nodes/theme_orchestrator.py) | 替代 research_dispatcher（market_study 唯一入口） |
| [backend/nodes/cross_validator.py](backend/nodes/cross_validator.py) | LLM 跨主题审查 |
| [backend/nodes/compactor.py](backend/nodes/compactor.py) | ThemeReport → editor 骨架 |
| [backend/nodes/citation_resolver.py](backend/nodes/citation_resolver.py) | `[cite:doc_id]` → `[N]` |

### 7.3 改造
| 路径 | 改动 |
|---|---|
| [backend/classes/state.py](backend/classes/state.py) | 替换为 `ResearchState`（见 §5.1） |
| [backend/classes/config.py](backend/classes/config.py) | 删除 `REPORT_TYPE_CONFIGS`；保留 `DEPTH_CONFIGS`、`SEMAPHORE_*`、`QUALITY_THRESHOLDS` |
| [backend/graph.py](backend/graph.py) | 单一 market_study 子图；删除 evaluator-retry 循环（cross_validator 接管） |
| [backend/prompts.py](backend/prompts.py) | 全量替换为中文 prompt：7 个主题专属 + 1 个自定义通用 + 1 个 editor（9 章节中文） + 1 个 cross_validator |
| [backend/query_prompts.py](backend/query_prompts.py) | 中文化 + 7 主题各一份；自定义主题用通用模板 |
| [backend/nodes/editor.py](backend/nodes/editor.py) | 中文 + V5 章节顺序 + 自定义主题排序 + 跳过未勾选 + 保留 `[cite:doc_id]` |
| [backend/nodes/output_formatter.py](backend/nodes/output_formatter.py) | 新增 word 输出（`python-docx`） |
| [backend/services/pdf_service.py](backend/services/pdf_service.py) | 中文字体（思源黑体）打包入容器 |
| [backend/services/mongodb_service.py](backend/services/mongodb_service.py) | 新增 `clarifications`、`agent_traces`、`checkpoints` 集合操作；删除 battlecard 相关 |
| [api.py](api.py) | 删除旧端点；新增 §4.7 中的新端点 |
| [requirements.txt](requirements.txt) | 加 `python-docx`；保留其他 |

### 7.4 复用（不动）
- LangGraph 编译模式 [graph.py:70](backend/graph.py) `_build_graph()`
- TypedDict + Annotated reducer 模式
- Exa 调用与重试 [base.py:68](backend/nodes/researchers/base.py)（保留 BaseResearcher 作为 ThemeSubAgent 内部工具）
- curated_ref MongoDB 引用模式 [curator.py:279](backend/nodes/curator.py)
- SSE 事件流 [graph.py:247](backend/graph.py) + [api.py:316](api.py)
- 质量评分 [curator.py:62](backend/nodes/curator.py) `_quality_score`
- Semaphore 并发控制
- Editor 流式 token 输出

---

## 8. 关键 Prompt 设计要点

### 8.1 输入助手（domain_validator）
- GPT-4.1-mini，structured output
- 倾向保守：默认 confirmed=true，仅高置信度才打断
- 输出含 `understood_as`，让用户能一眼对照

### 8.2 ThemeSubAgent 通用规则（所有主题共享）
- 中文输出；引用源原文可英文
- 每个事实陈述后必须跟 `[cite:doc_id]`，否则陈述会被审查删除
- 时间范围：start/end 之外的数据明确标注"数据缺失"
- 地理范围：多选时必须覆盖所有勾选地区，并做跨地区对比
- 来源优先级：政策→gov.cn/ndrc.gov.cn/miit.gov.cn；技术→Gartner/IEEE；投融资→IT桔子/Crunchbase；通用→新华社/财新；优先来源占比目标 ≥60%
- 输出 ThemeReport JSON schema（见 §5.2）

### 8.3 自定义主题专用
- prompt 加入用户输入的主题名作为唯一上下文
- 不强制表格 schema，但要求"如适用请用 Markdown 表格"
- 仍强制引用与中文

### 8.4 cross_validator
- Gemini 2.5 Flash，输入所有 ThemeReports
- 检查项：跨主题事实冲突 / 引用与原文不符（抽查） / 信息缺口未声明
- 输出 ValidationReport：可触发 sub-agent 重采（最多 1 次）或加 quality_flags

### 8.5 editor（中文，V5 章节）
- 强制章节顺序（§3.7）
- 未勾选主题跳过、编号顺延
- 保留所有 `[cite:doc_id]`，由 citation_resolver 后处理
- 流式 SSE 输出

---

## 9. 非功能需求

| 项 | 要求 |
|---|---|
| 性能 | standard 深度下，10 主题（7+3）全跑 < 8 分钟（受 Semaphore 控制） |
| 中文字体 | PDF/Word 内置思源黑体，部署在 Docker image |
| 可观测 | 每次 LLM 调用 trace 必须落库；前端 TracesDrawer 可时序回看 |
| 恢复 | 单 sub-agent 失败不拖累其他；崩溃后 `/resume` 从最后 checkpoint 续跑 |
| 安全 | 沿用现有 CORS 配置；Railway 域名自动放行 |
| 兼容 | 一次性切换，不保留 competitor 兼容层 |

---

## 10. 验证方案

### 10.1 单元/模块测试
```bash
python -m backend.evals.eval_module1   # state + market_study_config
python -m backend.evals.eval_module2   # theme_sub_agent + theme_orchestrator
python -m backend.evals.eval_module3   # cross_validator + compactor
python -m backend.evals.eval_module4   # citation_resolver + editor prompt
```
（原 module4 中的 comparator/battlecard 测试删除，替换为新内容）

### 10.2 端到端实跑
```bash
# Step 1: 歧义输入
curl -X POST http://localhost:8000/api/research/validate_domain \
  -d '{"domain": "新能源电池"}'
# → SSE：{"confirmed": false, "ambiguities": [...]}

# Step 2: 清晰输入
curl -X POST http://localhost:8000/api/research/validate_domain \
  -d '{"domain": "中国新能源汽车动力电池市场"}'
# → {"confirmed": true, "understood_as": "..."}

# Step 3: 问卷
curl -X POST http://localhost:8000/api/research/clarify \
  -d '{"confirmed_domain": "中国新能源汽车动力电池市场"}'
# → { clarification_id, ... }

# Step 4: 启动（含自定义主题）
curl -X POST http://localhost:8000/api/research/confirm \
  -d '{
    "clarification_id": "...",
    "selected_themes": ["market_size","industry_chain","competitive_landscape","policy","tech_trend","investment"],
    "custom_themes": ["ESG与可持续发展"],
    "geography": ["cn","us","eu"],
    "time_range": {"start": "2021-05", "end": "2031-05"},
    "depth": "standard",
    "output_format": "word"
  }'
# → { job_id }

# Step 5: 流 + 报告 + 轨迹 + 下载
curl http://localhost:8000/api/research/{job_id}/stream
curl http://localhost:8000/api/research/{job_id}/report
curl http://localhost:8000/api/research/{job_id}/traces
curl http://localhost:8000/api/research/{job_id}/download?format=word -o report.docx
```

### 10.3 V5 达成检查表
| 要求 | 检查 | 等级 |
|---|---|---|
| 两轮对话 | validate_domain + clarify + confirm 三端点串联 | 必须 |
| 7 主题完整覆盖 | 默认勾选下报告含全部 7 章节 | 必须 |
| 部分勾选生效 | 勾选 3 个主题时报告只含 3 章节，编号连续 | 必须 |
| 自定义主题 | 含自定义主题时，主题排在固定 7 章之后、参考清单之前 | 必须 |
| 中文输出 | 报告整体中文（引用源原文可英文） | 必须 |
| 时间范围生效 | sub-agent 查询和评分以 start/end 过滤；以 today 为界区分历史/预测 | 必须 |
| 地理范围生效 | 多选地理时报告含跨地区对比 | 必须 |
| 内联溯源 | `[N]` 可解析到 URL + excerpt | 必须 |
| 末尾参考清单 | 始终输出，编号顺延 | 必须 |
| 输出格式 | md/pdf/word 三格式正常下载 | 必须 |
| Agent Traces | `/traces` 返回完整 LLM 调用序列 | 必须 |
| Checkpointing/Resume | kill 一个 sub-agent 后 `/resume` 能从断点继续 | 必须 |
| 每章节 ≥ 1 表格 | Editor prompt 强写要求 | 尽力而为 |
| 历史/预测分段 | Editor + sub-agent prompt 强写要求 | 尽力而为 |

---

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 输入助手误判（清晰领域被判歧义） | prompt 偏保守；前端允许"忽略助手，强制进入问卷" |
| sub-agent context 隔离导致跨主题信息丢失 | cross_validator 重新审视所有 ThemeReport |
| 中文 PDF/Word 字体缺失 | 思源黑体显式集成到容器镜像 |
| Exa 中文搜索质量 | sub-agent prompt 同时生成中英文查询（国内源用中文、海外源用英文） |
| 10 主题并发 LLM 成本 | Semaphore 严格限速；snapshot/standard/deep_dive 控制每主题查询深度 |
| 政策类主题时效性 | AUTHORITATIVE_DOMAINS 显式包含 gov.cn / ndrc.gov.cn / miit.gov.cn / 行业协会 |
| 用户取消勾选所有主题/地理 | 前端校验阻止 Confirm，至少 1 主题（默认+自定义）+ 1 地理 |
| 时间范围超出 Exa 历史窗口 | sub-agent prompt 明确"超出可查询窗口部分注明数据缺失" |
| 删除 competitor 后用户找不到旧报告 | `research_jobs` 历史保留，但旧 schema 文档在 `/history` 仅展示 domain 字段（兼容兜底） |

---

## 12. 关键文件清单总览

### 新增
- [backend/classes/market_study_config.py](backend/classes/market_study_config.py)
- [backend/services/domain_validator_service.py](backend/services/domain_validator_service.py)
- [backend/services/clarification_service.py](backend/services/clarification_service.py)
- [backend/services/citation_service.py](backend/services/citation_service.py)
- [backend/services/trace_service.py](backend/services/trace_service.py)
- [backend/nodes/sub_agents/theme_sub_agent.py](backend/nodes/sub_agents/theme_sub_agent.py)
- [backend/nodes/theme_orchestrator.py](backend/nodes/theme_orchestrator.py)
- [backend/nodes/cross_validator.py](backend/nodes/cross_validator.py)
- [backend/nodes/compactor.py](backend/nodes/compactor.py)
- [backend/nodes/citation_resolver.py](backend/nodes/citation_resolver.py)
- [frontend/src/components/InputAssistant.tsx](frontend/src/components/InputAssistant.tsx)
- [frontend/src/components/ClarificationPanel.tsx](frontend/src/components/ClarificationPanel.tsx)
- [frontend/src/components/TracesDrawer.tsx](frontend/src/components/TracesDrawer.tsx)

### 改造
- [backend/classes/state.py](backend/classes/state.py)
- [backend/classes/config.py](backend/classes/config.py)
- [backend/graph.py](backend/graph.py)
- [backend/prompts.py](backend/prompts.py)
- [backend/query_prompts.py](backend/query_prompts.py)
- [backend/nodes/editor.py](backend/nodes/editor.py)
- [backend/nodes/output_formatter.py](backend/nodes/output_formatter.py)
- [backend/services/pdf_service.py](backend/services/pdf_service.py)
- [backend/services/mongodb_service.py](backend/services/mongodb_service.py)
- [api.py](api.py)
- [requirements.txt](requirements.txt)
- [frontend/src/components/Sidebar.tsx](frontend/src/components/Sidebar.tsx)
- [frontend/src/components/ReportViewer.tsx](frontend/src/components/ReportViewer.tsx)
- [frontend/src/hooks/useResearch.ts](frontend/src/hooks/useResearch.ts)
- [frontend/src/types/index.ts](frontend/src/types/index.ts)

### 删除
- [backend/nodes/comparator.py](backend/nodes/comparator.py)
- [backend/nodes/battlecard_builder.py](backend/nodes/battlecard_builder.py)
- [backend/services/discovery_service.py](backend/services/discovery_service.py)
- competitor 相关 researchers（保留 BaseResearcher 作为 ThemeSubAgent 工具）
- [frontend/src/components/DiscoveryPanel.tsx](frontend/src/components/DiscoveryPanel.tsx)
- 旧 `/discover`、`/start`、`/edit`、`/battlecard` 端点

---

## 13. 落地执行步骤（vibe coding，一次性完整交付）

> 不分 Phase，按依赖顺序滚动开发。每写完一组就跑 evals + 手测一次。

1. **配置与 schema 层**：market_study_config + state 改造 + config 瘦身 + requirements 加 python-docx
2. **后端服务层**：domain_validator_service + clarification_service + citation_service + trace_service
3. **后端节点层**：theme_sub_agent（含 7 个主题 prompt + 自定义 prompt）→ theme_orchestrator → cross_validator → compactor → citation_resolver → editor 中文化 → output_formatter 加 word
4. **图编排**：graph.py 单一 market_study 子图
5. **API 层**：api.py 删旧端点 + 加新端点 + traces + resume
6. **删除 competitor 全链路**：comparator / battlecard / discovery_service / 旧 researchers / 旧 prompts / 旧 evals
7. **前端**：Sidebar 瘦身 → InputAssistant → ClarificationPanel → useResearch phase 扩展 → ReportViewer 引用渲染 + word 下载 → TracesDrawer
8. **PDF/Word 中文字体**：Dockerfile 装思源黑体；pdf_service 切字体
9. **Evals 重写**：module1-4 替换内容
10. **端到端实跑**：按 §10.2 完整链路走 1 次，对照 §10.3 检查表逐项核

完成上述 10 步 = 基础版本交付。表格密集 / 历史预测分段属 best-effort（prompt 已写要求），实际效果由 LLM 决定，不阻塞交付。
