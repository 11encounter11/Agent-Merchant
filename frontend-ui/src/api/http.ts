import type {
  DashboardPlan,
  Preference,
  RangeKey,
  RuleCategoriesResponse,
  RuleDetail,
  RuleFeed,
  RuleSearchResponse,
} from '../types'

const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')
const TOKEN = (import.meta.env.VITE_AGENT_TOKEN || '').trim()

export class ApiError extends Error {
  readonly status: number
  readonly detail: string
  readonly errorCode: string
  readonly requestId: string

  constructor(status: number, detail: string, errorCode = '', requestId = '') {
    super(detail || `请求失败（${status}）`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.errorCode = errorCode
    this.requestId = requestId
  }
}

export function isBackendOffline(error: unknown): boolean {
  if (error instanceof TypeError) return true
  // Vite 代理在后端未启动时返回空 body 的 500；真实接口 500 会带 detail。
  return error instanceof ApiError && error.status === 500 && !error.detail
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  return {
    ...extra,
    ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: headers({ 'Content-Type': 'application/json', ...(init.headers as Record<string, string> || {}) }),
  })
  const text = await response.text()
  let payload: unknown = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = text
  }
  if (!response.ok) {
    let detail = ''
    let errorCode = ''
    let requestId = response.headers.get('X-Request-ID') || ''
    if (payload && typeof payload === 'object') {
      const body = payload as { detail?: unknown; error_code?: unknown; request_id?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (body.detail !== undefined) detail = JSON.stringify(body.detail)
      if (body.error_code) errorCode = String(body.error_code)
      if (body.request_id) requestId = String(body.request_id)
    }
    throw new ApiError(response.status, detail, errorCode, requestId)
  }
  return payload as T
}

export function fetchDashboard(range: RangeKey, refresh = false): Promise<DashboardPlan> {
  const query = new URLSearchParams({ range, refresh: String(refresh) })
  return request<DashboardPlan>(`/api/workbench/dashboard?${query.toString()}`)
}

export function fetchPreferences(): Promise<{ preferences: Preference[]; total: number }> {
  return request('/api/workbench/preferences')
}

export function createPreference(payload: {
  metric: string
  chart_type: string
  cadence: string
  range_key: RangeKey
  title?: string
}): Promise<{ success: boolean; preference: Preference }> {
  return request('/api/workbench/preferences', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function deletePreference(id: number): Promise<{ success: boolean }> {
  return request(`/api/workbench/preferences/${id}`, { method: 'DELETE' })
}

export function fetchRules(): Promise<RuleFeed> {
  return request<RuleFeed>('/api/workbench/rules')
}

export function fetchRuleCategories(): Promise<RuleCategoriesResponse> {
  return request<RuleCategoriesResponse>('/api/workbench/rules/categories')
}

export function searchRules(params: {
  q?: string
  category?: string
  page?: number
  size?: number
}): Promise<RuleSearchResponse> {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.category) query.set('category', params.category)
  query.set('page', String(params.page || 1))
  query.set('size', String(params.size || 20))
  return request<RuleSearchResponse>(`/api/workbench/rules/search?${query.toString()}`)
}

export function fetchRuleDetail(ruleId: string, section = ''): Promise<RuleDetail> {
  const query = new URLSearchParams()
  if (section) query.set('section', section)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return request<RuleDetail>(`/api/workbench/rules/${encodeURIComponent(ruleId)}${suffix}`)
}

export { API_BASE, TOKEN }
