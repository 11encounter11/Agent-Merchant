<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { chartAmber, chartGrid, chartText, useChart } from '../lib/chart'
import { selectWidget, state, widgetById } from '../store/workbench'
import type { RefundData } from '../types'

const widget = computed(() => widgetById('refund_trend'))
const data = computed<RefundData | null>(() => (widget.value?.data as RefundData | null) || null)
const el = ref<HTMLDivElement | null>(null)
const selectedDate = computed(() => {
  if (state.context?.widget_id !== 'refund_trend') return ''
  return String(state.context.selection.date || '')
})

function pickDate(event: Event): void {
  const date = (event.target as HTMLSelectElement).value
  if (date) {
    selectWidget('refund_trend', { date }, `退款趋势 · ${date}`)
  }
}

function build(): EChartsOption {
  if (!data.value) return {}
  return {
    animationDuration: 260,
    grid: { left: 44, right: 18, top: 24, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#17202b',
      borderWidth: 0,
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (params: unknown) => {
        const first = (Array.isArray(params) ? params[0] : params) as { dataIndex?: number; axisValue?: string } | undefined
        const index = first?.dataIndex ?? 0
        return `${first?.axisValue || ''}<br/>退款 ¥${Number(data.value?.amounts[index] || 0).toFixed(2)}<br/>退款单 ${data.value?.orders[index] || 0} 笔`
      },
    },
    xAxis: {
      type: 'category',
      data: data.value.dates.map((date) => date.slice(5)),
      boundaryGap: false,
      axisLine: { lineStyle: { color: chartGrid } },
      axisTick: { show: false },
      axisLabel: { color: chartText, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: chartGrid } },
      axisLabel: { color: chartText, fontSize: 10 },
    },
    series: [{
      name: '退款金额',
      type: 'line',
      data: data.value.amounts,
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { color: chartAmber, width: 2.2 },
      itemStyle: { color: chartAmber },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(199,134,58,.22)' },
            { offset: 1, color: 'rgba(199,134,58,.01)' },
          ],
        },
      },
    }],
  }
}

useChart(el, build, [() => data.value], (params) => {
  if (!data.value || params.dataIndex === undefined) return
  const date = data.value.dates[params.dataIndex]
  if (!date) return
  selectWidget('refund_trend', { date }, `退款趋势 · ${date}`)
})
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div>
        <div class="card-title">退款趋势</div>
        <div class="card-sub">{{ data?.note || '整单金额近似，按取消时间归日' }}</div>
      </div>
      <span class="pill warn">近似口径</span>
    </div>
    <div v-if="data && data.dates.length" ref="el" class="chart-box" role="img" aria-label="退款金额趋势图" />
    <div v-if="data && data.dates.length" class="a11y-row">
      <label class="a11y-picker">
        键盘选择
        <select :value="selectedDate" aria-label="键盘选择退款日期" @change="pickDate">
          <option value="">选择日期</option>
          <option v-for="date in data.dates" :key="date" :value="date">{{ date }}</option>
        </select>
      </label>
    </div>
    <div v-else class="empty-state">
      <div>
        <strong>退款数据暂不可用</strong>
        {{ widget?.error || '区间内没有退款记录。' }}
      </div>
    </div>
  </section>
</template>
