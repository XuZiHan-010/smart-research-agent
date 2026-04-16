// ── Domain types ──────────────────────────────────────────────────────────────

export type ReportType =
  | 'full_analysis'
  | 'pricing_focus'
  | 'investor_teardown'
  | 'customer_voice'
  | 'custom'

export type ResearchDepth  = 'snapshot' | 'standard' | 'deep_dive'
export type OutputFormat   = 'markdown' | 'pdf' | 'json'
export type ReportLanguage = 'en' | 'zh'
export type AppPhase       = 'idle' | 'discovering' | 'confirming' | 'running' | 'completed' | 'failed'
export type CellStatus     = 'pending' | 'success' | 'partial' | 'empty' | 'error'

// ── Config constants ──────────────────────────────────────────────────────────

export const REPORT_TYPE_OPTIONS: { value: ReportType; label: string; description: string }[] = [
  { value: 'full_analysis',    label: 'Full Analysis',      description: 'Comprehensive 360° across all 6 dimensions' },
  { value: 'pricing_focus',    label: 'Pricing Focus',      description: 'Product features and pricing comparison' },
  { value: 'investor_teardown',label: 'Investor Teardown',  description: 'Growth metrics, funding, moats' },
  { value: 'customer_voice',   label: 'Customer Voice',     description: 'Reviews, sentiment, churn signals' },
  { value: 'custom',           label: 'Custom',             description: 'Upload your own template' },
]

export const DEPTH_CONFIG: Record<ResearchDepth, { label: string; estimate: string; description: string }> = {
  snapshot:  { label: 'Snapshot',  estimate: '~5 min',  description: '2 queries/dim · fast overview · good for first pass' },
  standard:  { label: 'Standard',  estimate: '~15 min', description: '4 queries/dim · balanced depth and speed · recommended' },
  deep_dive: { label: 'Deep Dive', estimate: '~30 min', description: '6 queries/dim · maximum coverage · critical decisions' },
}

export const DIMENSION_LABELS: Record<string, string> = {
  product_pricing:    'Product & Pricing',
  market_position:    'Market Position',
  traction_growth:    'Traction & Growth',
  customer_sentiment: 'Customer Sentiment',
  content_gtm:        'Content & GTM',
  recent_activity:    'Recent Activity',
}

// ── Input models ──────────────────────────────────────────────────────────────

export interface CompanyInput {
  name:    string
  website: string
  source:  'user' | 'discovered' | 'target'
}

export interface DiscoverySuggestion {
  name:            string
  website:         string
  reason:          string
  score:           number
  default_checked: boolean
}

export interface ResearchConfig {
  target_company: string
  target_website: string
  report_type:    ReportType
  depth:          ResearchDepth
  output_format:  OutputFormat
  language:       ReportLanguage
  template:       string
  // competitors entered manually (before discovery)
  competitorNames: string[]
}

// ── Pipeline types ────────────────────────────────────────────────────────────

export type PipelineNodeId =
  | 'router' | 'grounding' | 'research_dispatcher'
  | 'collector' | 'curator' | 'evaluator'
  | 'comparator' | 'battlecard_builder' | 'editor' | 'output_formatter'

export interface PipelineStage {
  id:      PipelineNodeId
  label:   string
  status:  'idle' | 'active' | 'done' | 'error'
  message?: string
}

export interface TodoCell {
  status:    CellStatus
  docs_found: number
}

export type TodoState = Record<string, Record<string, TodoCell>>

// ── SSE event union ───────────────────────────────────────────────────────────

export interface StatusEvent {
  type:       'status'
  node?:      string
  dimension?: string
  company?:   string
  message:    string
}

export interface TodoEvent {
  type:       'todo'
  todo_state: TodoState
  dim_labels: Record<string, string>
}

export interface StreamEvent {
  type:    'stream'
  content: string
  node?:   string
}

export interface CompleteEvent {
  type:    'complete'
  job_id:  string
  report:  string
}

export interface ErrorEvent {
  type:    'error'
  job_id?: string
  message: string
}

export type SSEEvent = StatusEvent | TodoEvent | StreamEvent | CompleteEvent | ErrorEvent

// ── Battlecard schema ─────────────────────────────────────────────────────────

export interface FeatureRow {
  feature:   string
  companies: Record<string, 'yes' | 'partial' | 'no' | 'unknown'>
}

export interface PricingRow {
  company:      string
  model:        string
  entry_price:  string | null
  enterprise:   string | null
}

export interface WinLoseTheme {
  vs_competitor: string
  theme:         string
  evidence:      string
}

export interface ObjectionHandler {
  objection: string
  response:  string
}

export interface BattlecardData {
  target:             string
  competitors:        string[]
  feature_matrix:     FeatureRow[]
  pricing_comparison: PricingRow[]
  win_themes:         WinLoseTheme[]
  lose_themes:        WinLoseTheme[]
  key_risks:          string[]
  objection_handlers: ObjectionHandler[]
  generated_at:       string
  parse_error?:       string
}

// ── History ───────────────────────────────────────────────────────────────────

export interface HistoryJob {
  id:              string
  target_company:  string
  competitors:     string[]
  report_type:     ReportType
  depth:           ResearchDepth
  output_format:   OutputFormat
  status:          'running' | 'completed' | 'failed'
  created_at:      string
  completed_at?:   string
}
