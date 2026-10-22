export type RangeKey = 'yesterday' | 'last7' | 'last30' | 'this_week' | 'this_month'

export interface DataStatus {
  key: string
  label: string
  start: string
  end: string
  effective_start: string
  effective_end: string
  requested_start: string
  requested_end: string
  latest_data_date: string | null
  fallback_reason: string | null
  gap: boolean
  refund_approximation: boolean
  store_dimension: boolean
  data_as_of: string
}

export interface KpiCard {
  key: string
  label: string
  value: number | null
  unit: string
  previous: number | null
  change_rate: number | null
  metric: string
}

export interface KpiData {
  cards: KpiCard[]
}

export interface SalesData {
  dates: string[]
  values: number[]
  orders: number[]
  comparison: { dates: string[]; values: number[] } | null
  anomaly_dates: string[]
}

export interface DishItem {
  item_type: 'dish' | 'setmeal'
  item_id: string
  name: string
  qty: number
  amount: number
}

export interface DishData {
  items: DishItem[]
}

export interface RefundData {
  dates: string[]
  amounts: number[]
  orders: number[]
  approximation: boolean
  note: string
}

export interface HeatCell {
  weekday: number
  hour: number
  orders: number
}

export interface HeatmapData {
  weekday_labels: string[]
  cells: HeatCell[]
  max: number
}

export interface Widget {
  widget_id: string
  title: string
  chart_type: string
  metric: string
  snapshot_id: string
  selection_keys: string[]
  layout: 'full' | 'wide' | 'half'
  data: KpiData | SalesData | DishData | RefundData | HeatmapData | null
  meta: { unit: string; grain: string; note: string }
  error?: string
}

export interface Anomaly {
  type: string
  severity: string
  date: string
  title: string
  detail: string
  selection: Record<string, string>
}

export interface Unavailable {
  key: string
  reason: string
  message: string
}

export interface DashboardPlan {
  snapshot_id: string
  generated_at: string
  plan_version: string
  range: { key: string; label: string; start: string; end: string }
  data_status: DataStatus
  ai_brief: { generated_by: string; text: string; suggested_questions: string[] }
  widgets: Widget[]
  anomalies: Anomaly[]
  preferences_applied: Array<{ metric: string; chart_type: string; cadence: string }>
  unavailable: Unavailable[]
  partial: boolean
  errors: Array<{ key: string; message: string }>
}

export interface Preference {
  id: number
  metric: string
  chart_type: string
  cadence: string
  range_key: string
  title: string
  active?: boolean
  created_at?: string
  updated_at?: string
}

export interface RuleItem {
  rule_id: string
  title: string
  section: string
  category?: string
  effective_date: string
  status: string
  source: string
  demo?: boolean
  score?: number
  snippet: string
}

export interface RuleSearchItem extends RuleItem {
  score: number
}

export interface RuleSearchResponse {
  items: RuleSearchItem[]
  total: number
  page: number
  size: number
}

export interface RuleDetail extends RuleItem {
  content: string
}

export interface RuleCategoryItem {
  key: string
  label: string
  count: number
}

export interface RuleCategoriesResponse {
  categories: RuleCategoryItem[]
}

export interface CalendarItem {
  name: string
  date: string
  type: string
  impact: string
  text: string
}

export interface ActivityItem {
  activity_key: string
  title: string
  start_date: string
  end_date: string
  status: string
  description: string
  source: string
}

export interface RuleFeed {
  status: 'ok' | 'empty'
  reason: string
  rules: RuleItem[]
  activities: ActivityItem[]
  activity_status: 'ok' | 'empty'
  calendar: CalendarItem[]
  unavailable: Unavailable[]
}

export interface WidgetContext {
  widget_id: string
  snapshot_id: string
  selection: Record<string, string | number>
  range_key: string
  title: string
}

export interface ChatCitation {
  rule_id: string
  title: string
  section: string
  effective_date: string
  status?: string
  score?: number
  snippet?: string
  source?: string
  demo?: boolean
}

export type MessagePart =
  | { type: 'text'; text: string }
  | { type: 'tool'; name: string; status: 'running' | 'success'; summary?: string }
  | { type: 'citation'; citation: ChatCitation }
  | { type: 'usage'; totalTokens: number }
  | { type: 'note'; text: string; tone?: 'info' | 'warn' }

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  parts: MessagePart[]
  time: string
}
