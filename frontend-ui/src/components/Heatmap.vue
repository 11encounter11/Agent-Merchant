<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { chartGrid, chartText, useChart } from '../lib/chart'
import { selectWidget, widgetById } from '../store/workbench'
import type { HeatmapData } from '../types'

const widget = computed(() => widgetById('order_heatmap'))
const data = computed<HeatmapData | null>(() => (widget.value?.data as HeatmapData | null) || null)
const el = ref<HTMLDivElement | null>(null)
const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const options = computed(() =>
  (data.value?.cells || [])
    .filter((cell) => cell.orders > 0)
    .sort((a, b) => a.weekday - b.weekday || a.hour - b.hour),
)

function pickCell(event: Event): void {
  const [weekday, hour] = (event.target as HTMLSelectElement).value.split('-').map(Number)
  if (!weekday || Number.isNaN(hour)) return
  selectWidget('order_heatmap', { weekday, hour }, `时段热力 · ${weekdays[weekday - 1]} ${String(hour).padStart(2, '0')}:00`)
}

function build(): EChartsOption {
  if (!data.value) return {}
  const cells = data.value.cells.map((cell) => [cell.hour, cell.weekday - 1, cell.orders])
  return {
    animationDuration: 240,
    grid: { left: 42, right: 16, top: 10, bottom: 46 },
    tooltip: {
      backgroundColor: '#17202b',
      borderWidth: 0,
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (params: unknown) => {
        const value = (params as { value?: number[] }).value || []
        return `${weekdays[Number(value[1])] || ''} ${String(value[0]).padStart(2, '0')}:00<br/>完成订单 ${value[2] || 0} 单`
      },
    },
    xAxis: {
      type: 'category',
      data: Array.from({ length: 24 }, (_, hour) => `${String(hour).padStart(2, '0')}`),
      splitArea: { show: true },
      axisLine: { lineStyle: { color: chartGrid } },
      axisTick: { show: false },
      axisLabel: { color: chartText, fontSize: 10, interval: 2 },
    },
    yAxis: {
      type: 'category',
      data: weekdays,
      splitArea: { show: true },
      axisLine: { lineStyle: { color: chartGrid } },
      axisTick: { show: false },
      axisLabel: { color: chartText, fontSize: 11 },
    },
    visualMap: {
      min: 0,
      max: Math.max(1, data.value.max),
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemWidth: 10,
      itemHeight: 80,
      textStyle: { color: chartText, fontSize: 10 },
      inRange: { color: ['#f2f0ea', '#dbe6ff', '#9fbaff', '#2f6bff'] },
    },
    series: [{
      type: 'heatmap',
      data: cells,
      label: { show: false },
      itemStyle: { borderColor: '#fff', borderWidth: 2, borderRadius: 3 },
      emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(23,32,43,.25)' } },
    }],
  }
}

useChart(el, build, [() => data.value], (params) => {
  const value = (params as { value?: number[] }).value
  if (!value) return
  const hour = Number(value[0])
  const weekday = Number(value[1]) + 1
  selectWidget('order_heatmap', { weekday, hour }, `时段热力 · ${weekdays[weekday - 1]} ${String(hour).padStart(2, '0')}:00`)
})
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div>
        <div class="card-title">时段热力</div>
        <div class="card-sub">{{ widget?.meta?.note || '完成订单按星期 × 小时聚合，空白为 0' }}</div>
      </div>
      <span class="pill">7 × 24</span>
    </div>
    <div v-if="data" ref="el" class="chart-box" role="img" aria-label="星期与小时订单热力图" />
    <div v-if="data && options.length" class="a11y-row">
      <label class="a11y-picker">
        键盘选择
        <select aria-label="键盘选择热力时段" @change="pickCell">
          <option value="">选择时段</option>
          <option v-for="cell in options" :key="cell.weekday + '-' + cell.hour" :value="cell.weekday + '-' + cell.hour">
            {{ weekdays[cell.weekday - 1] }} {{ String(cell.hour).padStart(2, '0') }}:00 · {{ cell.orders }} 单
          </option>
        </select>
      </label>
    </div>
    <div v-else class="empty-state">
      <div>
        <strong>热力数据暂不可用</strong>
        {{ widget?.error || '区间内没有完成订单。' }}
      </div>
    </div>
  </section>
</template>
