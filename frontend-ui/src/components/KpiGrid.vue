<script setup lang="ts">
import { computed } from 'vue'
import { selectWidget, state, widgetById } from '../store/workbench'
import type { KpiCard } from '../types'

const widget = computed(() => widgetById('kpi_cards'))
const cards = computed<KpiCard[]>(() => {
  const data = widget.value?.data as { cards?: KpiCard[] } | null
  return data?.cards || []
})
const noData = computed(() => state.plan?.data_status.fallback_reason === 'NO_DATA_AT_ALL')
const selectedMetric = computed(() => {
  if (state.context?.widget_id !== 'kpi_cards') return ''
  return String(state.context.selection.metric || '')
})

function valueText(card: KpiCard): string {
  if (noData.value || card.value === null || card.value === undefined) return '—'
  if (card.unit === 'ratio') return `${(Number(card.value) * 100).toFixed(2)}%`
  if (card.unit === 'CNY') return `¥${Number(card.value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  return Number(card.value).toLocaleString('zh-CN')
}

function unitText(card: KpiCard): string {
  if (card.unit === 'order') return '单'
  if (card.unit === 'user') return '人'
  return ''
}

function deltaText(card: KpiCard): string {
  if (card.change_rate === null || card.change_rate === undefined) return '无对比'
  const value = Number(card.change_rate) * 100
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`
}

function deltaTone(card: KpiCard): string {
  if (card.change_rate === null || card.change_rate === undefined) return 'muted'
  const change = Number(card.change_rate)
  if (Math.abs(change) < 0.0005) return 'muted'
  const lowerIsBetter = card.key === 'refund_rate'
  const good = lowerIsBetter ? change < 0 : change >= 0
  return good ? 'positive' : 'negative'
}

function pick(card: KpiCard): void {
  selectWidget('kpi_cards', { metric: card.key }, card.label)
}
</script>

<template>
  <section class="card kpi-card-wrap" aria-labelledby="kpi-title">
    <div class="card-head">
      <div>
        <div id="kpi-title" class="card-title">经营 KPI</div>
        <div class="card-sub">点击任一指标，把它作为问题带进对话</div>
      </div>
      <span class="card-hint">{{ state.plan?.range.label || '' }}</span>
    </div>
    <div v-if="cards.length" class="kpi-grid">
      <button
        v-for="card in cards"
        :key="card.key"
        type="button"
        class="kpi-card"
        :class="{ selected: selectedMetric === card.key }"
        :aria-pressed="selectedMetric === card.key"
        @click="pick(card)"
      >
        <span class="kpi-label">
          {{ card.label }}
          <span class="tiny muted">{{ card.metric }}</span>
        </span>
        <span class="kpi-value">
          {{ valueText(card) }}<small v-if="unitText(card)">{{ unitText(card) }}</small>
        </span>
        <span class="kpi-foot">
          <span class="kpi-delta" :class="deltaTone(card)">{{ deltaText(card) }}</span>
          <span>较前一等长区间</span>
        </span>
      </button>
    </div>
    <div v-else class="empty-state">
      <div>
        <strong>KPI 暂不可用</strong>
        数据源未返回指标，请稍后刷新。
      </div>
    </div>
  </section>
</template>

<style scoped>
.kpi-card-wrap { padding: 18px; }
</style>
