import type { DashboardPlan, RuleFeed } from '../types'

const dates = ['2026-07-22', '2026-07-23', '2026-07-24', '2026-07-25', '2026-07-26', '2026-07-27', '2026-07-28']
const values = [171, 60, 0, 0, 420, 0, 8]
const orders = [2, 1, 0, 0, 3, 0, 1]

const heatCells = Array.from({ length: 7 }, (_, weekdayIndex) =>
  Array.from({ length: 24 }, (_, hour) => {
    const weekday = weekdayIndex + 1
    const hits: Record<string, number> = { '2:18': 1, '3:17': 2, '4:11': 1, '7:17': 2, '7:19': 1 }
    return { weekday, hour, orders: hits[`${weekday}:${hour}`] || 0 }
  }),
).flat()

export const mockPlan: DashboardPlan = {
  snapshot_id: 'mock_dashboard',
  generated_at: '2026-10-20T17:00:00+08:00',
  plan_version: '1',
  range: { key: 'yesterday', label: '昨日', start: '2026-07-22', end: '2026-07-29' },
  data_status: {
    key: 'yesterday',
    label: '昨日',
    start: '2026-07-22',
    end: '2026-07-29',
    effective_start: '2026-07-22',
    effective_end: '2026-07-29',
    requested_start: '2026-10-19',
    requested_end: '2026-10-20',
    latest_data_date: '2026-07-28',
    fallback_reason: 'NO_DATA_IN_REQUESTED_WINDOW',
    gap: true,
    refund_approximation: true,
    store_dimension: false,
    data_as_of: '2026-10-20T17:00:00+08:00',
  },
  ai_brief: {
    generated_by: 'rule',
    text:
      '请求的「昨日」没有支付订单；最近有数据的一天是 2026-07-28，已自动改为展示最近 7 个完整日。' +
      '这 7 天营业额 ¥659.00，完成 7 单；销售额第一是「超值单人餐」（¥192.00）。退款为整单近似。',
    suggested_questions: [
      '为什么 7 月 26 日卖得好？',
      '哪些菜品拖累客单价？',
      '退款率正常吗？平台退款规则怎么规定？',
    ],
  },
  widgets: [
    {
      widget_id: 'kpi_cards',
      title: '经营 KPI',
      chart_type: 'kpi',
      metric: 'revenue',
      snapshot_id: 'mock_dashboard',
      selection_keys: ['metric'],
      layout: 'full',
      data: {
        cards: [
          { key: 'revenue', label: '营业额', value: 659, unit: 'CNY', previous: 453, change_rate: 0.4547, metric: 'completed_net_revenue' },
          { key: 'orders', label: '完成订单', value: 7, unit: 'order', previous: 6, change_rate: 0.1667, metric: 'completed_order_count' },
          { key: 'aov', label: '客单价', value: 94.14, unit: 'CNY', previous: 75.5, change_rate: 0.2469, metric: 'average_order_value' },
          { key: 'refund_rate', label: '退款率', value: 0, unit: 'ratio', previous: 0.01, change_rate: -1, metric: 'refund_rate' },
          { key: 'new_customers', label: '新客', value: 0, unit: 'user', previous: 1, change_rate: -1, metric: 'new_customer_count' },
        ],
      },
      meta: { unit: 'mixed', grain: 'range', note: '' },
    },
    {
      widget_id: 'sales_trend',
      title: '销售额趋势',
      chart_type: 'line',
      metric: 'revenue',
      snapshot_id: 'mock_dashboard',
      selection_keys: ['date'],
      layout: 'wide',
      data: {
        dates,
        values,
        orders,
        comparison: { dates, values: [120, 80, 0, 0, 300, 0, 0] },
        anomaly_dates: [],
      },
      meta: { unit: 'CNY', grain: 'day', note: '' },
    },
    {
      widget_id: 'dish_top10',
      title: '菜品 / 套餐 Top10',
      chart_type: 'bar',
      metric: 'dish_sales',
      snapshot_id: 'mock_dashboard',
      selection_keys: ['item_type', 'item_id'],
      layout: 'half',
      data: {
        items: [
          { item_type: 'setmeal', item_id: '1', name: '超值单人餐', qty: 2, amount: 192 },
          { item_type: 'dish', item_id: '2', name: '老坛酸菜鱼', qty: 2, amount: 112 },
          { item_type: 'dish', item_id: '3', name: '清蒸鲈鱼', qty: 1, amount: 98 },
          { item_type: 'setmeal', item_id: '4', name: '轻食双人餐', qty: 1, amount: 98 },
          { item_type: 'dish', item_id: '5', name: '蜀味烤鱼', qty: 1, amount: 88 },
          { item_type: 'dish', item_id: '6', name: '米饭 2 份', qty: 1, amount: 68 },
          { item_type: 'dish', item_id: '7', name: '鸡蛋汤', qty: 1, amount: 66 },
          { item_type: 'dish', item_id: '8', name: '餐具', qty: 5, amount: 10 },
        ],
      },
      meta: { unit: 'CNY', grain: 'range', note: '销售额按单价 × 数量，含套餐' },
    },
    {
      widget_id: 'refund_trend',
      title: '退款趋势',
      chart_type: 'line',
      metric: 'refund_amount',
      snapshot_id: 'mock_dashboard',
      selection_keys: ['date'],
      layout: 'half',
      data: { dates, amounts: dates.map(() => 0), orders: dates.map(() => 0), approximation: true, note: '整单金额近似，按取消时间归日' },
      meta: { unit: 'CNY', grain: 'day', note: '整单金额近似，按取消时间归日' },
    },
    {
      widget_id: 'order_heatmap',
      title: '时段热力',
      chart_type: 'heatmap',
      metric: 'order_heatmap',
      snapshot_id: 'mock_dashboard',
      selection_keys: ['weekday', 'hour'],
      layout: 'half',
      data: {
        weekday_labels: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
        cells: heatCells,
        max: 2,
      },
      meta: { unit: 'order', grain: 'weekday_hour', note: '按完成订单补满 7×24 格' },
    },
  ],
  anomalies: [],
  preferences_applied: [],
  unavailable: [
    { key: 'channel_filter', reason: 'NO_DATA_COLUMN', message: '现有订单表没有渠道字段' },
    { key: 'review_widget', reason: 'NO_DATA_TABLE', message: '评价与评分数据未接入' },
    { key: 'platform_activity', reason: 'NO_DATA_TABLE', message: '平台没有活动表/活动 API' },
    { key: 'store_dimension', reason: 'NO_STORE_COLUMN', message: '订单表无 store_id，当前为商家级看板' },
  ],
  partial: false,
  errors: [],
}

export const mockRules: RuleFeed = {
  status: 'empty',
  reason: 'RULE_CORPUS_MISSING',
  rules: [],
  activities: [],
  activity_status: 'empty',
  calendar: [
    { name: '元旦', date: '2027-01-01', type: '法定假日', impact: '中', text: '2026年元旦是1月1日至1月3日' },
    { name: '春节', date: '2027-02-17', type: '法定假日', impact: '高', text: '2026年春节是2月17日至2月23日' },
  ],
  unavailable: [
    { key: 'platform_activity', reason: 'NO_ACTIVITY_FEED', message: '活动目录为空；平台导出活动 JSON 后会自动展示' },
    { key: 'formal_rule_corpus', reason: 'RULE_CORPUS_MISSING', message: '规则库未收录；等待导入真实条款' },
  ],
}
