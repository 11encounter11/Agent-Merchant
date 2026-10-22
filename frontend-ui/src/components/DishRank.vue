<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import { chartBlue, chartGrid, chartText, useChart } from '../lib/chart'
import { selectWidget, widgetById } from '../store/workbench'
import type { DishData } from '../types'

const widget = computed(() => widgetById('dish_top10'))
const data = computed<DishData | null>(() => (widget.value?.data as DishData | null) || null)
const items = computed(() => (data.value?.items || []).slice(0, 10))
const el = ref<HTMLDivElement | null>(null)

function shortName(name: string): string {
  return name.length > 10 ? `${name.slice(0, 10)}…` : name
}

function pickItem(event: Event): void {
  const key = (event.target as HTMLSelectElement).value
  const item = items.value.find((entry) => `${entry.item_type}:${entry.item_id}` === key)
  if (item) {
    selectWidget('dish_top10', { item_type: item.item_type, item_id: item.item_id }, `菜品 · ${item.name}`)
  }
}

function build(): EChartsOption {
  const rows = [...items.value].reverse()
  return {
    animationDuration: 260,
    grid: { left: 8, right: 42, top: 4, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#17202b',
      borderWidth: 0,
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (params: unknown) => {
        const first = (Array.isArray(params) ? params[0] : params) as { dataIndex?: number } | undefined
        const item = rows[first?.dataIndex ?? 0]
        return item ? `${item.name}<br/>销售额 ¥${item.amount.toFixed(2)}<br/>售出 ${item.qty} 份` : ''
      },
    },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: chartGrid } },
      axisLabel: { color: chartText, fontSize: 10 },
    },
    yAxis: {
      type: 'category',
      data: rows.map((item) => shortName(item.name)),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#394353', fontSize: 11 },
    },
    series: [{
      type: 'bar',
      data: rows.map((item) => item.amount),
      barWidth: 11,
      itemStyle: {
        borderRadius: [0, 6, 6, 0],
        color: {
          type: 'linear', x: 0, y: 0, x2: 1, y2: 0,
          colorStops: [
            { offset: 0, color: 'rgba(47,107,255,.35)' },
            { offset: 1, color: chartBlue },
          ],
        },
      },
    }],
  }
}

useChart(el, build, [() => data.value], (params) => {
  const rows = [...items.value].reverse()
  const item = rows[params.dataIndex ?? 0]
  if (!item) return
  selectWidget('dish_top10', { item_type: item.item_type, item_id: item.item_id }, `菜品 · ${item.name}`)
})
</script>

<template>
  <section class="card dish-card">
    <div class="card-head">
      <div>
        <div class="card-title">菜品 / 套餐 Top10</div>
        <div class="card-sub">{{ widget?.meta?.note || '销售额 = 单价 × 数量，含套餐' }}</div>
      </div>
      <span class="pill">{{ items.length }} 项</span>
    </div>
    <div v-if="items.length" ref="el" class="chart-box tall" role="img" aria-label="菜品销售额排行榜" />
    <div v-if="items.length" class="a11y-row">
      <label class="a11y-picker">
        键盘选择
        <select aria-label="键盘选择菜品" @change="pickItem">
          <option value="">选择菜品</option>
          <option v-for="item in items" :key="item.item_type + ':' + item.item_id" :value="item.item_type + ':' + item.item_id">
            {{ item.name }}
          </option>
        </select>
      </label>
    </div>
    <div v-else class="empty-state">
      <div>
        <strong>没有菜品销售</strong>
        {{ widget?.error || '区间内没有完成订单的菜品明细。' }}
      </div>
    </div>
  </section>
</template>

<style scoped>
.dish-card { min-height: 100%; }
</style>
