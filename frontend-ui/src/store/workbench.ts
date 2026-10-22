import { computed, reactive } from 'vue'
import {
  ApiError,
  createPreference,
  deletePreference,
  fetchDashboard,
  fetchPreferences,
  fetchRuleCategories,
  fetchRuleDetail,
  fetchRules,
  isBackendOffline,
  searchRules,
} from '../api/http'
import { streamChat } from '../api/chat'
import { mockPlan, mockRules } from '../mock/dashboard'
import type {
  ChatCitation,
  ChatMessage,
  DashboardPlan,
  MessagePart,
  Preference,
  RangeKey,
  RuleCategoryItem,
  RuleDetail,
  RuleFeed,
  RuleSearchItem,
  Widget,
  WidgetContext,
} from '../types'

export const rangeOptions: Array<{ key: RangeKey; label: string }> = [
  { key: 'yesterday', label: '昨日' },
  { key: 'last7', label: '近 7 日' },
  { key: 'last30', label: '近 30 日' },
  { key: 'this_week', label: '本周' },
  { key: 'this_month', label: '本月' },
]

const SESSION_KEY = 'sky_workbench_session'
const COMPOSER_HINTS: Record<string, string> = {
  kpi_cards: '这个指标为什么变化？',
  sales_trend: '为什么这一天销售额变化？哪些菜拖累？',
  dish_top10: '为什么这道菜卖得好？',
  refund_trend: '退款率正常吗？平台退款规则怎么规定？',
  order_heatmap: '为什么这个时段订单集中？',
}

function makeId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `m_${Date.now()}_${Math.random().toString(16).slice(2)}`
}

function nowTime(): string {
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(new Date())
}

function sessionId(): string {
  const saved = localStorage.getItem(SESSION_KEY)
  if (saved) return saved
  const created = makeId()
  localStorage.setItem(SESSION_KEY, created)
  return created
}

interface RuleCenterState {
  categories: RuleCategoryItem[]
  results: RuleSearchItem[]
  total: number
  page: number
  size: number
  query: string
  category: string
  loading: boolean
  error: string
  detail: RuleDetail | null
  detailLoading: boolean
  detailError: string
}

interface WorkbenchState {
  plan: DashboardPlan | null
  loading: boolean
  demo: boolean
  error: string
  range: RangeKey
  lastLoadedAt: string
  context: WidgetContext | null
  chatOpen: boolean
  composerText: string
  messages: ChatMessage[]
  streaming: boolean
  controller: AbortController | null
  preferences: Preference[]
  rules: RuleFeed | null
  toast: string
  rulesLoading: boolean
  ruleCenter: RuleCenterState
}

export const state = reactive<WorkbenchState>({
  plan: null,
  loading: false,
  demo: false,
  error: '',
  range: 'yesterday',
  lastLoadedAt: '',
  context: null,
  chatOpen: false,
  composerText: '',
  messages: [],
  streaming: false,
  controller: null,
  preferences: [],
  rules: null,
  toast: '',
  rulesLoading: false,
  ruleCenter: {
    categories: [],
    results: [],
    total: 0,
    page: 1,
    size: 5,
    query: '',
    category: '',
    loading: false,
    error: '',
    detail: null,
    detailLoading: false,
    detailError: '',
  },
})

let toastTimer: number | undefined
let dashboardToken = 0

function withRequestId(message: string, error: unknown): string {
  if (error instanceof ApiError && error.requestId) {
    return `${message}（请求号 ${error.requestId}）`
  }
  return message
}

export function notify(message: string): void {
  state.toast = message
  if (toastTimer) window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => { state.toast = '' }, 3200)
}

export const hasGap = computed(() => Boolean(state.plan?.data_status?.gap))
export const isMock = computed(() => state.demo)
export const widgetById = (id: string): Widget | undefined =>
  state.plan?.widgets.find((widget) => widget.widget_id === id)

export async function loadDashboard(refresh = false): Promise<void> {
  const token = ++dashboardToken
  state.loading = true
  state.error = ''
  try {
    const plan = await fetchDashboard(state.range, refresh)
    if (token !== dashboardToken) return
    state.plan = plan
    state.demo = false
  } catch (error) {
    if (token !== dashboardToken) return
    if (isBackendOffline(error)) {
      state.plan = mockPlan
      state.demo = true
      state.error = '后端服务未连接；当前展示演示数据，可稍后重试。'
    } else {
      state.plan = null
      state.demo = false
      state.error = error instanceof ApiError && error.status === 503
        ? withRequestId('数据库暂不可用，不是没有数据。请稍后重试。', error)
        : withRequestId((error as Error).message || '看板请求失败，请稍后重试。', error)
    }
  } finally {
    if (token === dashboardToken) {
      state.loading = false
      state.lastLoadedAt = nowTime()
    }
  }
}

export function setRange(range: RangeKey): void {
  if (state.range === range) return
  state.range = range
  clearContext()
  void loadDashboard(true)
}

export async function loadSidecars(): Promise<void> {
  state.rulesLoading = true
  try {
    const [prefs, ruleFeed] = await Promise.allSettled([fetchPreferences(), fetchRules()])
    state.preferences = prefs.status === 'fulfilled' ? prefs.value.preferences : []
    if (ruleFeed.status === 'fulfilled') {
      state.rules = ruleFeed.value
    } else if (isBackendOffline(ruleFeed.reason)) {
      state.rules = mockRules
    } else {
      state.rules = {
        status: 'empty',
        reason: 'RULE_FEED_UNAVAILABLE',
        rules: [],
        activities: [],
        activity_status: 'empty',
        calendar: [],
        unavailable: [{
          key: 'rules_service',
          reason: 'SERVICE_UNAVAILABLE',
          message: '规则服务暂不可用，请稍后刷新',
        }],
      }
    }
  } finally {
    state.rulesLoading = false
  }
}

export async function loadRuleCategories(): Promise<void> {
  try {
    const result = await fetchRuleCategories()
    state.ruleCenter.categories = result.categories
  } catch {
    state.ruleCenter.categories = []
  }
}

export async function searchRuleCenter(page = state.ruleCenter.page): Promise<void> {
  state.ruleCenter.loading = true
  state.ruleCenter.error = ''
  try {
    const result = await searchRules({
      q: state.ruleCenter.query.trim(),
      category: state.ruleCenter.category,
      page,
      size: state.ruleCenter.size,
    })
    state.ruleCenter.results = result.items
    state.ruleCenter.total = result.total
    state.ruleCenter.page = result.page
    state.ruleCenter.size = result.size
  } catch (error) {
    state.ruleCenter.error = withRequestId(
      (error as Error).message || '规则搜索暂不可用，请稍后重试。',
      error,
    )
    state.ruleCenter.results = []
    state.ruleCenter.total = 0
  } finally {
    state.ruleCenter.loading = false
  }
}

export async function loadRuleCenter(): Promise<void> {
  await Promise.all([loadRuleCategories(), searchRuleCenter(1)])
}

export async function openRuleDetail(rule: RuleSearchItem): Promise<void> {
  state.ruleCenter.detail = null
  state.ruleCenter.detailLoading = true
  state.ruleCenter.detailError = ''
  try {
    state.ruleCenter.detail = await fetchRuleDetail(rule.rule_id, rule.section)
  } catch (error) {
    state.ruleCenter.detailError = withRequestId(
      (error as Error).message || '规则详情暂不可用，请稍后重试。',
      error,
    )
  } finally {
    state.ruleCenter.detailLoading = false
  }
}

export function closeRuleDetail(): void {
  state.ruleCenter.detail = null
  state.ruleCenter.detailError = ''
  state.ruleCenter.detailLoading = false
}

export async function refreshRuleCenter(): Promise<void> {
  await Promise.all([loadSidecars(), loadRuleCenter()])
}

export function selectWidget(widgetId: string, selection: Record<string, string | number>, title: string): void {
  const widget = widgetById(widgetId)
  if (!widget || !state.plan) return
  state.context = {
    widget_id: widgetId,
    snapshot_id: widget.snapshot_id,
    selection,
    range_key: state.plan.range.key,
    title,
  }
  state.chatOpen = true
  if (!state.composerText.trim()) {
    state.composerText = COMPOSER_HINTS[widgetId] || '帮我解释一下这个图。'
  }
}

export function clearContext(): void {
  state.context = null
}

export function toggleChat(open?: boolean): void {
  state.chatOpen = open === undefined ? !state.chatOpen : open
}

export function useSuggestion(question: string): void {
  state.chatOpen = true
  state.composerText = question
}

function appendPart(message: ChatMessage, part: MessagePart): void {
  message.parts.push(part)
}

function appendText(message: ChatMessage, text: string): void {
  const last = message.parts[message.parts.length - 1]
  if (last && last.type === 'text') {
    last.text += text
  } else {
    message.parts.push({ type: 'text', text })
  }
}

function appendUsage(message: ChatMessage, data: Record<string, unknown>): void {
  const nested = data.token_usage && typeof data.token_usage === 'object'
    ? data.token_usage as Record<string, unknown>
    : {}
  const total = Number(data.total_tokens ?? nested.total_tokens ?? 0)
  if (Number.isFinite(total) && total > 0) {
    appendPart(message, { type: 'usage', totalTokens: Math.round(total) })
  }
}

function citationFrom(data: Record<string, unknown>): ChatCitation {
  return {
    rule_id: data.rule_id ? String(data.rule_id) : '',
    title: String(data.title || data.source || '参考来源'),
    section: data.section ? String(data.section) : '',
    effective_date: data.effective_date ? String(data.effective_date) : '',
    status: data.status ? String(data.status) : undefined,
    score: typeof data.score === 'number' ? data.score : undefined,
    snippet: data.snippet
      ? String(data.snippet)
      : (data.preview ? String(data.preview) : undefined),
    source: data.source ? String(data.source) : undefined,
    demo: Boolean(data.demo),
  }
}

export async function sendMessage(text: string): Promise<void> {
  const trimmed = text.trim()
  if (!trimmed || state.streaming) return
  state.chatOpen = true
  state.composerText = ''

  state.messages.push({ id: makeId(), role: 'user', parts: [{ type: 'text', text: trimmed }], time: nowTime() })
  const assistant: ChatMessage = { id: makeId(), role: 'assistant', parts: [], time: nowTime() }
  state.messages.push(assistant)
  state.streaming = true
  state.controller = new AbortController()

  const widgetContext = state.context
  let gotContent = false
  let gotError = false
  let verified: boolean | null = null

  try {
    await streamChat(
      { message: trimmed, sessionId: sessionId(), widgetContext },
      {
        onEvent(event, data) {
          if (event === 'content') {
            const content = String(data.content || '')
            if (content) {
              gotContent = true
              appendText(assistant, content)
            }
          } else if (event === 'tool_call') {
            appendPart(assistant, { type: 'tool', name: String(data.tool || 'tool'), status: 'running' })
          } else if (event === 'tool_result') {
            const name = String(data.tool || 'tool')
            const part = assistant.parts.find(
              (item): item is Extract<MessagePart, { type: 'tool' }> =>
                item.type === 'tool' && item.name === name && item.status === 'running',
            )
            if (part) {
              part.status = 'success'
              part.summary = String(data.result || '').slice(0, 120)
            } else {
              appendPart(assistant, { type: 'tool', name, status: 'success', summary: String(data.result || '').slice(0, 120) })
            }
          } else if (event === 'rag') {
            const hits = Array.isArray(data.hits) ? data.hits as Record<string, unknown>[] : []
            for (const hit of hits) {
              const citation = citationFrom(hit)
              const exists = assistant.parts.some(
                (item) => item.type === 'citation'
                  && item.citation.rule_id === citation.rule_id
                  && item.citation.section === citation.section,
              )
              if (!exists) appendPart(assistant, { type: 'citation', citation })
            }
          } else if (event === 'usage') {
            appendUsage(assistant, data)
          } else if (event === 'context') {
            verified = Boolean(data.verified)
            appendPart(assistant, {
              type: 'note',
              tone: verified ? 'info' : 'warn',
              text: verified ? '图表上下文已校验' : '图表快照已过期，回答会重新查数',
            })
          } else if (event === 'preference_saved') {
            const pref = data.preference as Preference | undefined
            appendPart(assistant, { type: 'note', tone: 'info', text: `已保存偏好：${pref?.title || '看板项'}` })
            void loadPreferences()
            void loadDashboard(true)
          } else if (event === 'dashboard_updated') {
            void loadDashboard(true)
          } else if (event === 'error') {
            gotError = true
            appendPart(assistant, { type: 'note', tone: 'warn', text: String(data.message || '服务处理失败') })
          }
        },
        onError(error) {
          gotError = true
          appendPart(assistant, { type: 'note', tone: 'warn', text: error.message })
        },
        onClose() {
          state.streaming = false
          state.controller = null
          if (!assistant.parts.length) {
            appendPart(assistant, { type: 'note', tone: 'warn', text: '没有收到回复，请稍后重试。' })
          } else if (!gotContent && verified === null && !gotError) {
            appendPart(assistant, { type: 'note', tone: 'warn', text: '本轮没有文本回复，请查看上方工具/引用信息。' })
          }
        },
      },
      state.controller.signal,
    )
  } catch (error) {
    if ((error as Error).name !== 'AbortError') {
      appendPart(assistant, { type: 'note', tone: 'warn', text: (error as Error).message })
    }
    state.streaming = false
    state.controller = null
  }
}

export function stopStreaming(): void {
  state.controller?.abort()
  state.controller = null
  state.streaming = false
}

export function retryLast(): void {
  if (state.streaming) return
  const last = state.messages[state.messages.length - 1]
  if (!last || last.role !== 'assistant') return
  let userIndex = state.messages.length - 2
  while (userIndex >= 0 && state.messages[userIndex].role !== 'user') {
    userIndex -= 1
  }
  if (userIndex < 0) return
  const user = state.messages[userIndex]
  const textPart = user.parts.find((part) => part.type === 'text')
  const text = textPart && textPart.type === 'text' ? textPart.text : ''
  if (!text.trim()) return
  state.messages.splice(userIndex)
  void sendMessage(text)
}

export async function loadPreferences(): Promise<void> {
  try {
    const result = await fetchPreferences()
    state.preferences = result.preferences
  } catch {
    state.preferences = []
  }
}

export async function addPreference(payload: {
  metric: string
  chart_type: string
  cadence: string
  range_key: RangeKey
  title?: string
}): Promise<void> {
  try {
    await createPreference(payload)
    await loadPreferences()
    await loadDashboard(true)
    notify('偏好已保存，看板已重新编排')
  } catch (error) {
    notify((error as Error).message)
  }
}

export async function removePreference(id: number): Promise<void> {
  try {
    await deletePreference(id)
    await loadPreferences()
    await loadDashboard(true)
    notify('偏好已删除')
  } catch (error) {
    notify((error as Error).message)
  }
}

export function resetSession(): void {
  localStorage.removeItem(SESSION_KEY)
  state.messages = []
  clearContext()
  notify('已开启新会话')
}
