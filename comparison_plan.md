# 评估：是否借鉴 DeerFlow 架构

**日期**: 2026-05-15  
**背景**: smart-research-agent 项目正在从竞品分析重构为市场调研工具。现有架构有多个已知痛点，DeerFlow 2.0 是一个更成熟的 LangGraph Agent 框架。

---

## 核心判断

**建议**: **有选择性地借鉴**，而非整体迁移。原因：

### 1. 不必整体迁移的原因

| 维度 | smart-research-agent | DeerFlow | 评价 |
|---|---|---|---|
| 工作流类型 | 线性 DAG（预定义 7 主题）| 通用 Agent（开放域任务分解） | 本项目场景更简单，强制使用 DeerFlow 的 `create_agent` 工厂会引入不必要复杂度 |
| 并发模式 | 单层 Theme × N（asyncio.gather）| 多层 Sub-Agent（线程池 + 轮询）| 本项目并发需求低（7-10 主题），线程池管理成本不划算 |
| 状态设计 | 自定义 TypedDict（已有）| 扩展 AgentState（14层中间件消费）| 本项目无中间件需求（无长期记忆、无 todo、无图片处理），自定义 State 更轻 |
| 引用处理 | 在 compactor 丢弃，后期重建 | 在系统提示中强制指导 | 需要改进，但不需要迁移整个中间件链 |

**结论**: 整体迁移 DeerFlow 架构会：
- 新增 14 个中间件（长期记忆、图片处理、计划跟踪等）9 成用不上
- 把异步 asyncio.gather 替换为线程池 + 轮询，性能下降
- 增加学习和维护成本（新团队成员需要理解中间件链）

---

## 值得借鉴的 3 个模式

### 模式 1：系统提示层的 Citation 指导（高优先级）

**问题现象**:
- 当前：`compactor` 在压缩 skeleton 时把 `citations` 字段丢弃了
- 结果：`editor` 收不到原始引用信息，只能依赖 narrative 内嵌的 `[cite:xxx]`
- 如果 LLM 漏写标记，citation_resolver 无从解析

**DeerFlow 做法**:
```python
# 在 system_prompt 中直接嵌入详细指导
"""
**CRITICAL: Always include citations when using web search results**
- Format: Use Markdown link format `[citation:TITLE](URL)` immediately after the claim
- Example: The key trends [citation:AI 2026](https://example.com)
- Sources Section: Collect all citations in "Sources" section at the end
  - ✅ RIGHT: `[Source Title](URL) - Description`
  - ❌ WRONG: `[citation:Title](URL)` 
"""
```

**借鉴方案**:
1. 在 `THEME_REPORT_PROMPT` 中加入详细的 citation 格式指导
2. 在 `EDITOR_MARKET_STUDY_PROMPT` 中强制说明「必须在报告中保留所有引用」
3. 改进 `citation_resolver` 的正则，处理多种格式
4. **不需要修改架构**——只是改进 prompt 工程

**工作量**: 低（2-3 小时），收益：高（大幅降低引用遗失率）

---

### 模式 2：质量门控的条件路由（中优先级）

**问题现象**:
- 当前：`cross_validator` 计算 `should_retry / confidence` 但无任何图边消费这些字段
- 如果某主题 confidence="low" 或 `should_retry=true`，流程照走到 editor，质量无保障

**DeerFlow 做法**:
```python
# 中间件层动态截断超限工具调用
class SubagentLimitMiddleware(AgentMiddleware):
    def after_model(self, state):
        # 如果并发子任务 > max_concurrent，截断后续任务并通知用户
        # 用户可以手动发起重试，而非盲目继续
```

**借鉴方案**:
在 `cross_validator` 后增加条件边：

```python
# graph.py 中替换当前的线性连接
def _should_retry(state):
    if not state["validation_report"]:
        return "compactor"  # 校验失败，skip validation
    
    should_retry = state["validation_report"].get("should_retry", False)
    if should_retry and state.get("retry_count", 0) < MAX_RETRIES:
        return "theme_orchestrator"  # 重新研究失败主题
    else:
        return "compactor"  # 通过或达到重试上限

# 在 cross_validator 节点后加入条件路由
graph.add_conditional_edges(
    "cross_validator",
    _should_retry,
    {"compactor": "compactor", "theme_orchestrator": "theme_orchestrator"}
)
```

**需要新增**:
- `ResearchState` 中新增 `retry_count` 和 `failed_themes`（用于 theme_orchestrator 识别哪些主题需要重做）
- 改进 `theme_orchestrator` 使其支持 partial retry（只研究失败的主题，不重做全部）

**工作量**: 中（5-8 小时），收益：中（质量保证，但增加延迟）

---

### 模式 3：流式输出的真正异步化（低优先级，技术债）

**问题现象**:
- 当前：`editor` 内部 `astream` 收集全部 tokens 后再 return，事件在节点完成时批量 yield
- 前端看到的是「卡顿再突然刷屏」，而非流畅逐 token 推送

**DeerFlow 做法**:
```python
# StreamBridge 解耦生产者和消费者
# 1. Agent 节点中的 stream 事件立即发布到 StreamBridge（不等节点完成）
# 2. 前端的 SSE 端点独立订阅 StreamBridge，获得实时事件
```

**借鉴方案**:
在 `api.py` 中引入一个轻量级事件队列：

```python
# 全局队列（类似 DeerFlow 的 MemoryStreamBridge）
_stream_queues: dict[str, asyncio.Queue] = {}

# 在 editor 节点内部：
async def node_editor(state, config):
    job_id = state["job_id"]
    if job_id not in _stream_queues:
        _stream_queues[job_id] = asyncio.Queue()
    
    queue = _stream_queues[job_id]
    
    async for chunk in chain.astream(...):
        await queue.put({"type": "stream", "content": chunk})  # 立即发布
        # 不等节点完成
    
    return {"report": full_report}

# SSE 端点改为直接消费队列
@app.get("/api/research/{job_id}/stream")
async def stream_research(job_id: str):
    async def event_generator():
        queue = _stream_queues[job_id]
        while True:
            event = await queue.get()
            if event.get("type") == "__end__":
                break
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**工作量**: 低（3-4 小时），收益：低（UX 改进，无功能影响）

---

## 不推荐借鉴的 DeerFlow 特性

| 特性 | 原因 |
|---|---|
| **14 层中间件链** | smart-research-agent 只需要 citation 和质量门控，不需要长期记忆、图片处理、澄清对话等 9 个中间件 |
| **线程池 + 轮询的 Sub-Agent** | 当前 theme_orchestrator 用 asyncio.gather 已经很高效，改成线程池会倒退 |
| **完整的 Agent 工厂 (create_agent)** | 项目的图结构已经确定，不需要 DeerFlow 的通用 Agent 工厂 |
| **Sandbox 集成** | market study 不涉及危险代码执行，无需沙箱 |
| **多模型混搭** | 当前模型分配策略足够（gpt-4.1-mini 用于 query/report，gpt-4.1 用于 editor，gemini 用于 validator），不需要 DeerFlow 的模型继承系统 |

---

## 推荐实施优先级

### Phase 1（高优先级，2-3 周）
**目标**: 修复 citation 遗失问题 + 清理死代码

- [ ] 改进 `THEME_REPORT_PROMPT` 和 `EDITOR_MARKET_STUDY_PROMPT` 中的 citation 指导（借鉴 DeerFlow）
- [ ] 删除死代码：`BaseResearcher`, `RESEARCHER_REGISTRY`, `queries_per_theme` 等 State 字段
- [ ] 重构 `compactor`，保留 `citations` 字段传递到 editor
- [ ] 改进 `citation_resolver`，支持多种引用格式

**验证**: 
```bash
python -m backend.evals.eval_module4  # 检查 battlecard + editor 的 citation 覆盖率
```

### Phase 2（中优先级，1-2 周）
**目标**: 实现质量门控和条件重试

- [ ] 在 graph 中添加条件边（借鉴 DeerFlow 的中间件思想，但简化为 Python 函数）
- [ ] 扩展 `ResearchState` 的 `retry_count / failed_themes`
- [ ] 改进 `theme_orchestrator`，支持 partial retry
- [ ] 添加 `max_research_retries` 到 config

**验证**:
```bash
python -m backend.evals.eval_pipeline  # 端到端测试，包含低质量主题的重试
```

### Phase 3（可选，技术债）
**目标**: 真正的流式输出

- [ ] 重构 editor SSE 机制，使用事件队列
- [ ] 前端消费实时 token streams

**验证**: 手动在前端监控 SSE 事件的到达时间间隔

---

## 风险与成本评估

| 借鉴方案 | 迁移成本 | 引入的依赖 | 向后兼容性 | 推荐度 |
|---|---|---|---|---|
| **Citation 指导** | 低 (2h) | 无新依赖 | 100% 兼容 | ⭐⭐⭐⭐⭐ |
| **条件路由** | 中 (5h) | 无新依赖 | 95% (新 retry 字段) | ⭐⭐⭐⭐ |
| **流式输出** | 低 (3h) | 无新依赖 | 100% 兼容 | ⭐⭐⭐ |
| **整体迁移到 DeerFlow** | 高 (40h+) | 新增 15 依赖 | 0% (重写) | ⭐ |

---

---

## 补充：Agentic RAG 的必要性分析

**新需求背景**：用户希望 Agent 更智能地决定搜索策略（而非预定义 7 个主题 × N 个固定查询）。

### 当前架构的限制

```
[User Input: "市场调研 + 7 个主题"] 
    ↓
[Router: 固定映射 7 个主题 → depth_params]
    ↓
[ThemeSubAgent × 7: 每个生成固定 queries_per_theme 个查询]
    ↓
[Exa 搜索 × (7 × queries): 并行搜索，无反馈循环]
    ↓
[聚合 → 合成报告]
```

**痛点**：
1. **无自适应**：第一轮搜索如果有知识空白，无法发现并针对性补充
2. **固定查询**：所有主题使用同一套 `queries_per_theme` 参数，无法根据搜索结果质量动态调整
3. **无迭代**：没有"检查信息完整性 → 补充搜索"的循环

### Agentic RAG 模式的潜力

```
[User Input + Research Goal]
    ↓
[Planner Agent: 分解为子问题 + 优先级排序]
    ↓
┌─[Researcher Agent #1]
│  ├─ Search based on goal
│  ├─ Evaluate result quality
│  ├─ If insufficient → Route to Researcher #2
│  └─ Return structured findings
│
├─[Researcher Agent #2 (如果需要)]
│  └─ Targeted follow-up search
│
└─[Synthesizer]: 聚合 + 撰写报告
```

**Agentic RAG 能解决**：
- ✅ Agent 根据初步结果判断"缺少什么"，发起第二轮搜索
- ✅ 动态调整关键词和搜索深度
- ✅ 处理开放式研究问题（不限于 7 个预定义主题）
- ✅ 真正的"搜索 → 评估 → 迭代"循环

### 实施成本对比

#### 方案 A：轻量级改进（**推荐，如果只需微调**）
- 在当前架构基础上，增强 `cross_validator` 的反馈
- `cross_validator` 识别低质量或缺失的维度 → 标记 `retry_themes`
- `theme_orchestrator` 支持 partial retry（只补充搜索失败的主题）
- **工作量**：5-8 小时（Phase 2 中已涵盖）
- **效果**：解决 60% 的问题（补充搜索，但仍是预定义主题）

#### 方案 B：完整 Agentic RAG（**需要架构重构**）

如果想要真正的 Agent 驱动搜索策略，需要：

1. **新增 Planner 节点**（LLM）
   - 接收研究目标 + 用户背景
   - 动态分解为 N 个子任务（不限于 7 个）
   - 分配优先级和深度参数

2. **改进 ThemeSubAgent**
   - 接收动态的 `research_goal`（不是固定的 7 个主题名称）
   - 返回 `completeness_score` 和 `gaps`（缺失的知识点）
   - 支持多轮迭代搜索

3. **新增 Quality Evaluator 环**（可用 LLM 或规则）
   - 评估"这个搜索结果足够吗？"
   - 如果不足，返回 Planner 补充搜索
   - 最多重试 3-5 轮

4. **改进 Editor**
   - 接收的不是 7 个固定章节，而是动态数量的主题
   - 自适应地组织内容

**工作量**：30-40 小时（完整重构）
**新增依赖**：无（仍用现有 LLM）
**向后兼容性**：需要改 API 入参（支持 open-ended research goal）

### 建议决策树

```
┌─ 问题：用户研究需求是"固定的 7 个维度"还是"开放式探索"？
│
├─ 如果是"固定 7 个维度"
│  └─→ 采用方案 A（轻量级）
│      └─ Phase 2：质量门控 + partial retry
│      └─ 成本：5-8 小时
│      └─ 推荐 ✅
│
└─ 如果是"开放式探索"或"用户自定义主题"
   └─→ 需要方案 B（Agentic RAG）
       ├─ 需要架构重构（30-40 小时）
       ├─ 或者迁移到 DeerFlow（40+ 小时 + 维护成本高）
       └─ 长期看，DeerFlow 更合适（已内置 Planner + Sub-Agents）
```

### 我的建议

**如果短期目标是"改进当前 7 主题工作流的搜索质量"**：
- 采用**方案 A**（轻量级）
- 实施 Phase 1 + Phase 2
- 成本：1-2 周，收益立竿见影

**如果长期目标是"支持开放式市场研究"（不限主题）**：
- 现在就迁移到 **DeerFlow**（前面的判断需要改变）
- 或者自建 Agentic RAG 框架
- 成本更高，但收益更大

---

## 总结与建议

### 最优策略：**分两阶段走**

**第一阶段（当前）**：轻量级借鉴 DeerFlow

DeerFlow 是一个为**通用 Agent（开放域问题分解）** 设计的框架。smart-research-agent 目前是一个 **Workflow（7 个预定义主题的结构化研究）**，两者的设计目标不同。

**具体建议**:

1. **立即行动**（Phase 1）：
   - 借鉴 DeerFlow 的 citation 系统提示方法
   - 清理死代码（BaseResearcher 等）
   - 这些改动无成本、低风险、高收益

2. **近期计划**（Phase 2）：
   - 借鉴 DeerFlow 的条件路由思想，但用 Python 函数而非中间件链
   - 实现质量门控和 partial retry（轻量级 agentic 能力）
   - 预计 1-2 周完成

**第二阶段（如果需要）**：评估是否升级到完整 Agentic RAG

- 如果用户研究需求变成"开放式、多轮迭代"，需要重新评估
- 此时可选择迁移到 DeerFlow（它已有 Planner + Multi-Agent 基础设施）
- 或自建 Agentic RAG（30-40 小时）

3. **不推荐（当前）**：
   - 整体迁移到 DeerFlow 框架（适合完全不同的使用场景）
   - 导入 DeerFlow 的中间件链（大部分用不上）

---

# 第二部分：前端 UI 重设计方案

## Context

后端架构从「线性 DAG」演进为「带反馈循环的轻量 Agentic Workflow」：
- 新增 `cross_validator → theme_orchestrator` 条件重试边
- 新增 partial retry（仅重做失败主题，可重试 1-2 轮）
- 改进 citation 处理（compactor 保留 citations，editor 强化引用指导）
- 真正流式 token 推送

**前端必须重新设计**以反映这些新概念：
- 从"线性进度条"变成"迭代循环图"
- 从"全部主题统一处理"变成"主题级质量分 + 单独重试可视化"
- Citation 从"裸编号 [1]"升级为"可探索的来源卡片"
- 暴露 Agent 的"决策瞬间"（决定重试、评估通过等）

---

## 当前前端清单（继承的资产）

**技术栈**：React 18 + TS + Vite + Tailwind + Framer Motion + lucide-react + react-markdown

**美学基调**（保留并强化）：
- 配色：`base #070b11`（深蓝黑）+ `accent #c9922a`（暗金）+ `active-green #22c55e` + `error-red #ef4444`
- 字体：**Cormorant**（衬线展示） / **DM Sans**（正文） / **JetBrains Mono**（数据/代码）
- 风格定位：**"研究终端 × 古典文献"** —— 高端金融终端的密度 + 衬线字体的学术气质

**现有组件**（重用）：
- [Sidebar.tsx](frontend/src/components/Sidebar.tsx) - 配置面板
- [ProgressTracker.tsx](frontend/src/components/ProgressTracker.tsx) - 进度可视化（**需要重做**）
- [ReportViewer.tsx](frontend/src/components/ReportViewer.tsx) - 报告展示（**需要增强 citation**）
- [ClarificationPanel.tsx](frontend/src/components/ClarificationPanel.tsx) - 范围确认
- [HistoryDrawer.tsx](frontend/src/components/HistoryDrawer.tsx) / [TracesDrawer.tsx](frontend/src/components/TracesDrawer.tsx)

---

## 设计哲学：The Loop（循环）

**核心隐喻**：研究不是流水线，而是**迭代精炼**。

```
            ┌─────────────────┐
            │  PLAN (Themes)  │
            └────────┬────────┘
                     ↓
       ┌───────► RESEARCH (parallel × 7) ◄────┐
       │             ↓                         │
       │         VALIDATE                      │ retry
       │             ↓                         │ failed
       │      ┌──── ◇ ────┐ ─────────────────┘
       │     OK         FAIL
       │      ↓
       └─►  WRITE → CITE → DELIVER
```

视觉上：用**圆环（orbit）+ 节点（nodes）+ 重试光弧（retry arc）** 代替线性流程图。

---

## 重新设计的页面流程

### 状态机变化

```ts
// types/index.ts 新增
export type AppPhase =
  | 'idle'
  | 'clarifying'
  | 'confirming_scope'
  | 'running'
  | 'completed'
  | 'failed'

// PipelineStage 新增字段
export interface PipelineStage {
  id: PipelineNodeId
  label: string
  status: 'idle' | 'active' | 'done' | 'error' | 'retrying'  // ← 新增 retrying
  message?: string
  iteration?: number  // ← 当前轮次
}

// 新增主题级状态
export interface ThemeRunState {
  theme_key: string
  label: string
  status: 'pending' | 'researching' | 'validating' | 'retrying' | 'done' | 'failed'
  docs_found: number
  quality_score?: number       // 0-100
  confidence?: 'high' | 'medium' | 'low'
  retry_count: number
  citations_count: number
  gaps?: string[]              // 缺失的知识点
}

export interface ValidationSnapshot {
  iteration: number
  overall_score: number
  flags: string[]              // ["低引用密度", "时间范围不足"...]
  retry_themes: string[]
  decision: 'pass' | 'retry' | 'force_pass'
  timestamp: string
}
```

### SSE 事件扩展

```ts
// 后端需要新增的事件类型
| { type: 'theme_progress'; theme_key: string; state: ThemeRunState }
| { type: 'validation'; snapshot: ValidationSnapshot }
| { type: 'retry'; iteration: number; themes: string[]; reason: string }
| { type: 'citation_resolved'; doc_id: string; title: string; url: string; index: number }
```

---

## 核心组件重设计（5 个）

### 1. `OrbitTracker` —— 替换现有 ProgressTracker

**布局**：占满左侧区域，分三段

```
┌─────────────────────────────────────────┐
│  Researching · Iteration 02            │  ← 顶部：当前研究领域 + 当前轮次
│  中国新能源汽车动力电池市场                  │
├─────────────────────────────────────────┤
│                                         │
│         ┌─ THEME ORBIT ─┐               │  ← 中部：环形主题状态
│        ◌                ◌               │     7 个主题环绕中心
│       ◌   ◉ (writing)   ◌               │     当前活跃节点高亮
│        ◌                ◌               │     重试主题有橙色光环
│         └────  ↻ ────┘                  │
│                                         │
├─────────────────────────────────────────┤
│  ▸ market_size       ████░░ 高 12 docs │  ← 底部：主题列表（可滚动）
│  ▸ industry_chain    ███░░░ 中 8 docs  │     展示进度条 + 置信度 + 文档数
│  ▸ competitive    ↻  ██░░░░ 低 4 docs  │     重试主题有 ↻ 标
│  ...                                    │
└─────────────────────────────────────────┘
```

**关键交互**：
- **环形节点**：7 个主题环绕在圆周上，活跃主题脉冲发光（accent 色）
- **重试光弧**：当 cross_validator 决定重试时，从环上发出一条橙色弧线划过整个环（用 SVG path + Framer Motion 实现）
- **节点点击**：弹出该主题的 Detail Drawer（展示已找到的 docs、查询、质量评估）
- **轮次计数器**：右上角显示 `Iteration 01 / Iteration 02` —— 关键 agentic 信号

**实现要点**（仅伪代码）：
```tsx
// SVG-based circular layout，半径 R = 140
themes.map((t, i) => {
  const angle = (i / 7) * Math.PI * 2 - Math.PI / 2
  const x = Math.cos(angle) * R, y = Math.sin(angle) * R
  return (
    <motion.circle
      cx={x} cy={y} r={t.status === 'researching' ? 14 : 10}
      animate={{ r: t.status === 'researching' ? [10, 14, 10] : 10 }}
      className={cn(
        t.status === 'done' && 'fill-active-green',
        t.status === 'retrying' && 'stroke-accent stroke-2 fill-accent/20',
        t.status === 'failed' && 'fill-error-red'
      )}
    />
  )
})

// Retry arc 用 SVG path 画从一点到另一点的圆弧
<motion.path
  d={arcPath(fromAngle, toAngle, R + 20)}
  stroke="#c9922a"
  strokeDasharray="200"
  initial={{ strokeDashoffset: 200 }}
  animate={{ strokeDashoffset: 0 }}
  transition={{ duration: 1.2 }}
/>
```

---

### 2. `ThemeDetailDrawer` —— 新建

点击 OrbitTracker 中的主题节点时滑出（右侧，500px 宽）。

**结构**：
```
┌──────────────────────────────────┐
│  竞争格局                      ×  │
│  Iteration 02 · Retrying         │
├──────────────────────────────────┤
│  Quality Score                   │
│  ████████░░ 68 / 100             │  ← 大号数字，带渐变光效
│                                  │
│  Flags                           │
│  • 引用密度不足（4/12 段落无源） │  ← 黄色 chip
│  • 时间分布偏旧（2024 前 70%）   │
│                                  │
│  Search Queries (Iter 02)        │
│  › "动力电池 市占率 2025"        │  ← 灰色 mono 字体
│  › "宁德时代 比亚迪 出货量"      │
│                                  │
│  Sources (8)                     │
│  ┌─ 36kr.com · 2025-09 ──────┐  │  ← 可点击卡片
│  │ 动力电池行业研究报告...      │  │
│  │ ▎▎▎▎▎ 高相关性                │  │
│  └────────────────────────────┘  │
│  ...                             │
└──────────────────────────────────┘
```

---

### 3. `ValidationTimeline` —— 新建

在 OrbitTracker 下方或单独的横向时间线，展示历次验证决策。

```
Iteration 01                Iteration 02 (current)
●─────────────────────────●─────────────────────  
72/100 · retry → 3 themes  pending...
```

- 每个节点 hover 展示该轮的 flags 详情
- 用户能直观感受到 "Agent 自己评估后决定再来一轮"

---

### 4. `ReportViewer` 增强：CitationHoverCard

**当前**：报告中只有 `[1] [2]` 数字。

**重做**：用 react-markdown 的 `components.a` 拦截器，把 `[N]` 渲染成带 hover 卡片的元素。

```tsx
const CitationLink = ({ index }: { index: number }) => {
  const citation = citationMap[index]
  return (
    <Tooltip
      content={
        <div className="w-80 p-3 bg-elevated border border-accent/30 shadow-2xl">
          <div className="font-mono text-[10px] text-accent uppercase">Source [{index}]</div>
          <h4 className="font-display text-base mt-1">{citation.title}</h4>
          <p className="text-text-secondary text-xs mt-2">{citation.excerpt}</p>
          <a href={citation.url} className="text-accent text-xs mt-2 block">
            {new URL(citation.url).hostname} ↗
          </a>
        </div>
      }
    >
      <sup className="text-accent border-b border-dotted border-accent/40 cursor-pointer hover:bg-accent/10 px-0.5">
        [{index}]
      </sup>
    </Tooltip>
  )
}
```

**报告末尾的 Sources 表**：从扁平列表改为**卡片网格**，每个来源可展开查看完整 excerpt + 在报告中出现的次数。

---

### 5. `ClarificationPanel` 微调

现有的范围确认面板（在 [ClarificationPanel.tsx](frontend/src/components/ClarificationPanel.tsx)）保持，但增加：
- **预估重试次数**：显示 `预计研究轮次：1-2 轮`（基于 depth）
- **质量门控开关**：允许用户选择 `严格 / 宽松 / 关闭` 三档 retry policy

---

## 美学强化点

### A. 排版细节
- 主标题用 **Cormorant Italic** 加重："Researching*.*" → "Iter*ating*."
- 数字（轮次、分数、文档数）一律 **JetBrains Mono Light**，加大字号制造高级感
- 中文标签保持 DM Sans，避免 Cormorant 渲染中文不一致

### B. 配色微调
- 引入 `retry-amber: #d97706`（橙色，区分于 accent 金色） —— 专属于"重试"概念的信号色
- 引入 `quality-grad: linear-gradient(90deg, #ef4444 0%, #c9922a 50%, #22c55e 100%)` —— 质量分数条专用

### C. 动效
- OrbitTracker 圆环：缓慢旋转（60s 一圈），仅在 active 状态下
- 重试时：橙色弧线扫过 + 整个环短暂震颤（`whileInView` + `motion.div animate={{ rotate: [0, -1, 1, 0] }}`)
- 报告流式 token：每个 chunk 出现时短暂的 `text-accent` 高亮 → 200ms 内淡回 `text-primary`（"刚生成"的视觉残留）

### D. 背景纹理
现有的纯色 `bg-base` 太平。可在主内容区加：
- 极淡的 SVG 网格背景（10% 透明度）
- 顶部一道光晕（`radial-gradient(ellipse at top, accent/8%, transparent 60%)`）

---

## 关键文件改动

| 文件 | 改动 |
|---|---|
| [frontend/src/types/index.ts](frontend/src/types/index.ts) | 新增 `ThemeRunState`, `ValidationSnapshot`, 扩展 `SSEEvent` 联合类型 |
| [frontend/src/hooks/useResearch.ts](frontend/src/hooks/useResearch.ts) | 处理 `theme_progress` / `validation` / `retry` 事件 |
| [frontend/src/components/ProgressTracker.tsx](frontend/src/components/ProgressTracker.tsx) | **重写**为 `OrbitTracker` |
| [frontend/src/components/ThemeDetailDrawer.tsx](frontend/src/components/ThemeDetailDrawer.tsx) | **新建** |
| [frontend/src/components/ValidationTimeline.tsx](frontend/src/components/ValidationTimeline.tsx) | **新建** |
| [frontend/src/components/ReportViewer.tsx](frontend/src/components/ReportViewer.tsx) | 增强 citation 渲染（HoverCard） |
| [frontend/src/components/Sidebar.tsx](frontend/src/components/Sidebar.tsx) | 加 retry policy 选择器 |
| [frontend/tailwind.config.js](frontend/tailwind.config.js) | 加 `retry-amber` 色、`quality-grad` |
| frontend/src/index.css | 加背景网格 / 光晕 |

---

## 实施分阶段

### Stage A（与后端 Phase 2 同步，1 周）
- 扩展 types 和 useResearch
- 实现 OrbitTracker（替换 ProgressTracker）
- 实现 ValidationTimeline

### Stage B（独立，1 周）
- ThemeDetailDrawer
- ReportViewer 的 CitationHoverCard

### Stage C（润色，3 天）
- 背景纹理、动效微调
- Sidebar 加 retry policy

---

## 验证方法

```bash
# 1. 后端启动（含 Phase 2 后端改动）
uvicorn api:app --host 0.0.0.0 --port 8000 --reload

# 2. 前端启动
cd frontend && npm run dev

# 3. 手动测试场景
# - 触发一次正常研究：观察 OrbitTracker 是否按顺序点亮各主题
# - 模拟低质量结果（mock cross_validator 返回 should_retry=true）：观察重试弧线动效
# - 点击主题节点：观察 ThemeDetailDrawer 是否展示正确的 docs / queries / quality
# - 报告完成后：hover citation 数字应弹出来源卡片，可点击跳转

# 4. 视觉验收清单
# □ Cormorant 衬线大标题清晰可见
# □ 暗金色 accent 与暗蓝底色对比强烈
# □ Iteration 计数器是用户能立刻看懂的"agentic 信号"
# □ 重试弧线动画 ≤ 1.5s，不影响阅读
```

---

## 不做的事

- ❌ 不引入新的 UI 框架（如 shadcn、MUI）—— 现有 Tailwind + Motion 足够
- ❌ 不改变整体配色（深蓝 + 暗金）—— 这是产品识别度
- ❌ 不做"AI 聊天"风格界面（如 ChatGPT 那种）—— 与产品定位不符
- ❌ 不做暗/亮模式切换 —— 当前深色版本是刻意的美学选择

