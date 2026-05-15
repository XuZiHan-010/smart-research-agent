export type ResearchDepth = 'snapshot' | 'standard' | 'deep_dive'
export type OutputFormat = 'markdown' | 'pdf' | 'word'
export type AppPhase =
  | 'idle'
  | 'clarifying'
  | 'confirming_scope'
  | 'running'
  | 'completed'
  | 'failed'

export type CellStatus = 'pending' | 'success' | 'partial' | 'empty' | 'error'

export const DEPTH_CONFIG: Record<ResearchDepth, { label: string; estimate: string; description: string }> = {
  snapshot: { label: 'Snapshot', estimate: '~5 min', description: '快速概览，适合判断方向' },
  standard: { label: 'Standard', estimate: '~15 min', description: '均衡覆盖，默认推荐' },
  deep_dive: { label: 'Deep Dive', estimate: '~30 min', description: '最大覆盖，适合正式决策' },
}

export const THEME_LABELS: Record<string, string> = {
  market_size: '市场规模与增长趋势',
  industry_chain: '产业链分析',
  products_applications: '主要产品、服务与应用场景',
  competitive_landscape: '竞争格局',
  policy: '政策与监管环境',
  tech_trend: '技术趋势',
  investment: '投融资、并购与战略合作动态',
}

export interface ResearchConfig {
  researchDomain: string
  depth: ResearchDepth
}

export interface ThemeOption {
  key: string
  label_zh: string
  checked: boolean
}

export interface GeographyOption {
  key: string
  label_zh: string
  checked: boolean
}

export interface ClarificationQuestionnaire {
  clarification_id: string
  research_domain: string
  themes: ThemeOption[]
  custom_themes_max: number
  geography_options: GeographyOption[]
  time_range: { start: string; end: string; today: string }
}

export interface ConfirmScopePayload {
  clarification_id: string
  selected_themes: string[]
  custom_themes: string[]
  geography: string[]
  time_range: { start: string; end: string; today: string }
  depth: ResearchDepth
  theme_depths: Record<string, ResearchDepth>
}

export type PipelineNodeId =
  | 'router'
  | 'theme_orchestrator'
  | 'cross_validator'
  | 'compactor'
  | 'editor'
  | 'citation_resolver'
  | 'output_formatter'

export interface PipelineStage {
  id: PipelineNodeId
  label: string
  status: 'idle' | 'active' | 'done' | 'error' | 'retrying'
  message?: string
  iteration?: number
}

// ── Agentic loop visualization ────────────────────────────────────────────────

export type ThemeStatus =
  | 'pending'
  | 'researching'
  | 'validating'
  | 'retrying'
  | 'done'
  | 'failed'

export type Confidence = 'high' | 'medium' | 'low'

export interface ThemeRunState {
  theme_key: string
  label: string
  status: ThemeStatus
  docs_found: number
  quality_score?: number
  confidence?: Confidence
  retry_count: number
  citations_count: number
  gaps?: string[]
  queries?: string[]
  sources?: ThemeSource[]
}

export interface ThemeSource {
  doc_id: string
  title: string
  url: string
  published?: string
  excerpt?: string
  score?: number
}

export interface ValidationSnapshot {
  iteration: number
  overall_score: number
  flags: string[]
  retry_themes: string[]
  decision: 'pass' | 'retry' | 'force_pass'
  timestamp: string
  reason?: string
}

export interface CitationRef {
  index: number
  doc_id: string
  title: string
  url: string
  excerpt?: string
  published?: string
}

export interface TodoCell {
  status: CellStatus
  docs_found: number
  label?: string
}

export type TodoState = Record<string, Record<string, TodoCell>>

export interface StatusEvent {
  type: 'status'
  node?: string
  message: string
}

export interface TodoEvent {
  type: 'todo'
  todo_state: TodoState
  dim_labels: Record<string, string>
}

export interface StreamEvent {
  type: 'stream'
  content: string
  node?: string
}

export interface CompleteEvent {
  type: 'complete'
  job_id: string
  report: string
}

export interface ErrorEvent {
  type: 'error'
  job_id?: string
  message: string
}

export interface ThemeProgressEvent {
  type: 'theme_progress'
  theme_key: string
  state: Partial<ThemeRunState> & { theme_key: string }
}

export interface ValidationEvent {
  type: 'validation'
  snapshot: ValidationSnapshot
}

export interface RetryEvent {
  type: 'retry'
  iteration: number
  themes: string[]
  reason?: string
}

export interface CitationEvent {
  type: 'citation_resolved'
  citation: CitationRef
}

export type SSEEvent =
  | StatusEvent
  | TodoEvent
  | StreamEvent
  | CompleteEvent
  | ErrorEvent
  | ThemeProgressEvent
  | ValidationEvent
  | RetryEvent
  | CitationEvent

export interface AgentTrace {
  created_at: string
  node: string
  model: string
  prompt_name: string
  input_summary: string
  output_summary: string
  metadata?: Record<string, unknown>
}

export interface HistoryJob {
  id: string
  research_domain: string
  selected_themes: string[]
  custom_themes: string[]
  geography: string[]
  depth: ResearchDepth
  output_format: OutputFormat
  theme_depths?: Record<string, ResearchDepth>
  status: 'running' | 'completed' | 'failed'
  created_at: string
  completed_at?: string
}
