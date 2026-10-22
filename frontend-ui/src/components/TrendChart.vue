<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { chartBlue, chartGrid, chartRed, chartText, useChart } from '../lib/chart'
import { selectWidget, state, widgetById } from '../store/workbench'
import type { SalesData } from '../types'

const widget = computed(() => widgetById('sales_trend'))
const data = computed<SalesData | null>(() => (widget.value?.data as SalesData | null) || null)
const el = ref<HTMLDivElement | null>(null)

const selectedDate = computed(() => {
  if (state.context?.widget_id !== 'sales_trend') return ''
  return String(state.context.selection.date || '')
})

function label(date: string): string {
  return date.slice(5)
}

function pickDate(event: Event): void {
  const date = (event.target as HTMLSelectElement).value
  if (date) {
    selectWidget('sales_trend', { date }, `销售额趋势 · ${date}`)
  }
}

function build(): EChartsOption {
  const values = data.value
  if (!values) return {}
  const amount = (value: number): string => `¥${Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
  return {
    animationDuration: 260,
    grid: { left: 44, right: 18, top: 28, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#17202b',
      borderWidth: 0,
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (params: unknown) => {
        const list = Array.isArray(params) ? params : [params]
        const first = list[0] as { dataIndex?: number; axisValue?: string } | undefined
        const index = first?.dataIndex ?? 0
        const current = values.values[index] ?? 0
        const compare = values.comparison?.values[index]
        const lines = [`${first?.axisValue || ''}`, `销售额 ¥${Number(current).toFixed(2)}`, `完成订单 ${values.orders[index] ?? 0} 单`]
        if (compare !== undefined) lines.push(`上期 ¥${Number(compare).toFixed(2)}`)
        return lines.join('<br/>')
      },
    },
    xAxis: {
      type: 'category',
      data: values.dates.map(label),
      boundaryGap: false,
      axisLine: { lineStyle: { color: chartGrid } },
      axisTick: { show: false },
      axisLabel: { color: chartText, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: chartGrid } },
      axisLabel: { color: chartText, fontSize: 10, formatter: (value: number) => value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value) },
    },
    series: [
      ...(values.comparison
        ? [{
            name: '上期',
            type: 'line' as const,
            data: values.comparison.values,
            smooth: false,
            symbol: 'none',
            lineStyle: { color: '#c3cad5', width: 1.5, type: 'dashed' as const },
            z: 1,
          }]
        : []),
      {
        name: '销售额',
        type: 'line',
        data: values.values.map((value, index) => ({
          value,
          symbol: values.anomaly_dates.includes(values.dates[index]) ? 'circle' : 'circle',
          symbolSize: values.anomaly_dates.includes(values.dates[index]) ? 9 : 5,
          itemStyle: { color: values.anomaly_dates.includes(values.dates[index]) ? chartRed : chartBlue },
        })),
        smooth: false,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: chartBlue, width: 2.4 },
        itemStyle: { color: chartBlue },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(47,107,255,.24)' },
              { offset: 1, color: 'rgba(47,107,255,.01)' },
            ],
          },
        },
        z: 3,
      },
    ],
  }
}

useChart(el, build, [() => data.value], (params) => {
  const current = data.value
  if (!current || params.dataIndex === undefined) return
  const date = current.dates[params.dataIndex]
  if (!date) return
  selectWidget('sales_trend', { date }, `销售额趋势 · ${date}`)
})
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div>
        <div class="card-title">销售额趋势</div>
        <div class="card-sub">{{ widget?.meta?.note || '按完成订单统计；虚线为上一等长区间' }}</div>
      </div>
      <div class="card-actions">
        <span class="pill info">点某天追问</span>
      </div>
    </div>
    <div v-if="data && data.dates.length" class="trend-wrap">
      <div ref="el" class="chart-box tall" role="img" aria-label="销售额趋势图" />
      <div v-if="selectedDate" class="selected-note">已选中 {{ selectedDate }} · 到右侧补充问题</div>
    </div>
    <div v-else class="empty-state">
      <div>
        <strong>区间内没有完成订单</strong>
        {{ widget?.error || '没有可绘制的销售数据。' }}
      </div>
    </div>
    <div class="legend-row">
      <span><i class="legend-dot blue" /> 本期销售额</span>
      <span v-if="data?.comparison"><i class="legend-dot gray" /> 上一等长区间</span>
      <span><i class="legend-dot red" /> 异常点</span>
      <label class="a11y-picker">
        键盘选择
        <select :value="selectedDate" aria-label="键盘选择销售额日期" @change="pickDate">
          <option value="">选择日期</option>
          <option v-for="date in data?.dates || []" :key="date" :value="date">{{ date }}</option>
        </select>
      </label>
    </div>
  </section>
</template>

<style scoped>
.trend-wrap { position: relative; }
.legend-row { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 8px; color: var(--muted); font-size: 11px; }
.legend-dot { display: inline-block; width: 7px; height: 7px; margin-right: 4px; border-radius: 50%; }
.legend-dot.blue { background: var(--blue); }
.legend-dot.gray { background: #c3cad5; }
.legend-dot.red { background: var(--red); }
.selected-note { position: absolute; right: 8px; top: 6px; padding: 4px 8px; border-radius: 8px; background: rgba(232,239,255,.9); color: #2454c8; font-size: 11px; }
</style>
