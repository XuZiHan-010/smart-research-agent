# Market Study Agent — 三项产品改进

## Context

针对 Market Study Agent v4.0 的三项体验改进：

1. **去除显式 topic 清晰度验证** — 当前 `domain_validator_service.py` 用 LLM 判断 topic 是否模糊，再让用户在 InputAssistant 里选择消歧选项。用户认为这一步多余、打断流程，希望由后续研究环节的 LLM 在 prompt 里自行理解 topic（隐式处理）。
2. **移除 Sidebar 的输出格式选择器** — 因为 `ReportViewer.tsx` 已经有 MD/PDF/Word 下载按钮，并且 `api.py` 的 `/download` 端点能按需重新转换任何格式，所以输入时让用户预选格式没有意义。
3. **按主题（theme）独立设置研究深度** — 当前 `graph.py` 的 router_node 把单一 `depth` 映射到全局 `queries_per_theme / results_per_query / max_docs_per_theme`，所有 ThemeSubAgent 共享。希望在 ClarificationPanel 里为每个勾选的固定主题 + 自定义主题各自配置 Snapshot/Standard/Deep Dive；Sidebar 的全局 depth 作为默认值。

预期效果：流程更短（少一个验证步骤）、UI 更干净（去掉重复的格式控件）、研究更精准（重点主题深挖、次要主题快速浏览）。

---

## 改动一：去除 domain validation 流程

### 前端
- `frontend/src/hooks/useResearch.ts:122-173` — 删除 `validateResearchDomain`、`chooseDomainOption`、`pendingConfig`、`assistantText`、`validationResult` 相关 state 与逻辑。
- `frontend/src/hooks/useResearch.ts:109-120` — 将 `requestQuestionnaire` 暴露为外部入口 `startClarification(config)`，由 Sidebar Start 直接触发。
- 新增 phase 流转：`idle → clarifying → confirming_scope → running`（去掉 `validating` 和 `ambiguous`）。`types/index.ts` 中 `AppPhase` 同步更新。
- `frontend/src/App.tsx` — 移除 `InputAssistant` 组件挂载；Sidebar `onStart` 直接走 questionnaire 流程。
- 删除 `frontend/src/components/InputAssistant.tsx`（无其他引用后）。

### 后端
- `api.py:51-53, 125-135` — 删除 `ValidateDomainRequest` 与 `/api/research/validate_domain` 端点。
- 删除 `backend/services/domain_validator_service.py` 及 `api.py:23` 的 import。
- **隐式 topic 理解** — 在 `backend/query_prompts.py` 和 `backend/prompts.py` 的 query 生成 prompt 顶部加一段指令："若 research_domain 模糊或宽泛，请基于该领域常见研究范畴自行选定一个合理的细分焦点，并在 query 里体现"。无需新代码，只改 prompt 文本。

---

## 改动二：移除 Sidebar 输出格式选择器

### 前端
- `frontend/src/components/Sidebar.tsx:15, 69-85` — 删除 `outputFormat` state 和"输出格式" section。
- `frontend/src/components/Sidebar.tsx:22` — `ResearchConfig` 不再包含 `outputFormat`；`types/index.ts` 同步删除字段。
- `frontend/src/components/ClarificationPanel.tsx:41` — `ConfirmScopePayload` 不再含 `output_format`。

### 后端
- `api.py:59-66` — `ConfirmRequest.output_format` 字段及 `api.py:99-100` 的校验删除。
- `api.py:169, 177, 187` — 所有 `output_format` 写入位置改为硬编码 `"markdown"`（或直接移除，让 Graph 默认值生效）。
- `backend/nodes/output_formatter.py:9-19` — 简化为只生成 markdown（PDF/Word 分支可保留函数本体，仅由 `/download` 端点调用）。`state.output_format` 字段在 `state.py:55` 保留为 optional 兼容历史 job。
- `api.py:273-295` 的 `/download` 端点不动——已支持按 query param 重新生成任意格式。

---

## 改动三：按主题独立研究深度

### 数据结构
- `backend/classes/state.py:54` — 保留 `depth` 字段作为默认值；新增 `theme_depths: Dict[str, str]`（key 为 `market_size`、`industry_chain`、…，以及自定义主题运行时 key `custom_1`、`custom_2`、`custom_3`）。
- `api.py:59-66` — `ConfirmRequest` 新增 `theme_depths: Dict[str, str] = Field(default_factory=dict)`。`_validate_confirm` 中校验所有值都属于 `VALID_DEPTHS`。

### 前端
- `frontend/src/types/index.ts` — `ConfirmScopePayload` 新增 `theme_depths: Record<string, ResearchDepth>`。
- `frontend/src/components/ClarificationPanel.tsx:14, 17, 60-66` —
  - 新增 state `themeDepths: Record<string, ResearchDepth>`，初始值用 `config.depth` 填充所有 themes（固定 + 自定义）。
  - 每个主题 checkbox 行旁加一个 3 选 1 的紧凑 segmented control（Snapshot/Standard/Deep Dive）；自定义主题同样加。
  - 主题取消勾选时无需从 themeDepths 删除（提交时按 selectedThemes 过滤）；自定义主题增删时同步 themeDepths 的 `custom_1/2/3` key。
- `frontend/src/components/ClarificationPanel.tsx:32-43` — 提交 payload 时构造 `theme_depths` —— 只包含 `selectedThemes + custom_1..N` 的有效 key。

### 后端
- `backend/graph.py:18-29` — `router_node` 不再写 `queries_per_theme / results_per_query / max_docs_per_theme` 三个全局字段（或保留为兜底默认）。新增 logic：构造 `theme_depth_params: Dict[str, Dict[str, int]]` 写入 state，key 为 theme_key，value 是该主题的三项 depth 参数。
- `backend/graph.py:56-89` — Graph 构造器：参数新增 `theme_depths: Dict[str, str]`，写入 `initial_state`。
- `backend/nodes/theme_orchestrator.py:21, 45-47` — 在 `run_one(theme_key, ...)` 内按 `state["theme_depths"].get(theme_key, state["depth"])` 查 `DEPTH_CONFIGS`，把该主题专属的三项参数传给 `ThemeSubAgent.run`。
- 自定义主题的 key 约定：orchestrator 内现有 `f"custom_{idx+1}"` 命名（`theme_orchestrator.py:16`），与前端 payload 中 `theme_depths` 的 key 必须一致。

### `/resume` 兼容
- `api.py:303-324` — `resume` 端点从 DB 读出的 job 中带上 `theme_depths`，传入 Graph。`db.create_job`（`api.py:162`）写入字段时新增 `theme_depths`。

---

## 关键文件清单

| 文件 | 改动类型 |
|---|---|
| frontend/src/components/Sidebar.tsx | 删除格式选择器 |
| frontend/src/components/ClarificationPanel.tsx | 主题旁加深度下拉、提交 theme_depths |
| frontend/src/components/InputAssistant.tsx | 删除文件 |
| frontend/src/hooks/useResearch.ts | 删除 validate 流程、暴露 startClarification |
| frontend/src/types/index.ts | AppPhase、ConfirmScopePayload、ResearchConfig 调整 |
| frontend/src/App.tsx | 去掉 InputAssistant 挂载 |
| api.py | 删除 validate 端点、ConfirmRequest 加 theme_depths、去掉 output_format 校验 |
| backend/services/domain_validator_service.py | 删除文件 |
| backend/classes/state.py | 新增 `theme_depths` 字段 |
| backend/graph.py | router 不再固定写全局 depth 字段；Graph 构造器加 theme_depths |
| backend/nodes/theme_orchestrator.py | 按 theme 查 depth_cfg |
| backend/nodes/output_formatter.py | 简化为只产 markdown |
| backend/query_prompts.py, backend/prompts.py | prompt 中加入"自行细化模糊 topic"的指令 |

---

## 验证

1. 启动后端 `python api.py`、前端 `cd frontend && npm run dev`。
2. **流程缩短** — 在 Sidebar 输入"低空经济"→ 点 Start，应直接跳到 ClarificationPanel，无 InputAssistant 中间步骤。
3. **格式选择已移除** — Sidebar 只剩"研究领域"+"研究深度"两个 section；Start 后 ClarificationPanel 同样不再有 output_format 选项；报告完成后 ReportViewer 的 MD/PDF/Word 下载按钮仍可工作。
4. **按主题 depth 生效** — 在 ClarificationPanel 把"市场规模"设为 Deep Dive、"政策与监管"设为 Snapshot，其他保持 Standard，提交。看 SSE `todo` 事件或后端 trace：market_size 应执行 ~7 queries、policy 应执行 ~2 queries。
5. **隐式 topic 理解** — 直接用"低空经济"（无地区/时间细化）跑一次 Standard，检查生成的 queries 是否合理地把范围聚焦到中国市场/无人机/eVTOL 等典型方向。
6. **回归** — 跑一次完整 Standard 全主题流程，确认 cross_validator、compactor、editor、citation_resolver 仍正常；MongoDB 中 job 文档包含 `theme_depths` 字段；`/api/research/{id}/resume` 能从 DB 恢复 theme_depths。
