import * as echarts from 'echarts'
import { nextTick, onBeforeUnmount, onMounted, watch, type Ref, type WatchSource } from 'vue'

type ClickHandler = (params: { dataIndex?: number; name?: string; value?: unknown }) => void

export function useChart(
  el: Ref<HTMLDivElement | null>,
  build: () => echarts.EChartsOption,
  sources: WatchSource[],
  onClick?: ClickHandler,
): void {
  let chart: echarts.ECharts | null = null
  let observer: ResizeObserver | null = null
  let observedEl: HTMLElement | null = null

  const observe = (node: HTMLElement): void => {
    if (observedEl === node) return
    observer?.disconnect()
    observedEl = node
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(node)
  }

  const ensureChart = (): echarts.ECharts | null => {
    if (!el.value) return null
    if (chart && chart.getDom() !== el.value) {
      chart.dispose()
      chart = null
    }
    if (!chart) {
      chart = echarts.init(el.value)
      if (onClick) chart.on('click', onClick)
      observe(el.value)
    }
    return chart
  }

  const render = (): void => {
    const instance = ensureChart()
    if (instance) instance.setOption(build(), true)
  }
  const resize = (): void => chart?.resize()

  onMounted(async () => {
    await nextTick()
    render()
    window.addEventListener('resize', resize)
  })
  // 图表容器是 v-if 渲染的：数据到达后必须等 DOM patch 完成再 init
  watch(sources, render, { deep: true, flush: 'post' })
  onBeforeUnmount(() => {
    window.removeEventListener('resize', resize)
    observer?.disconnect()
    observer = null
    observedEl = null
    chart?.dispose()
    chart = null
  })
}

export const chartText = '#68717d'
export const chartGrid = '#ece9e1'
export const chartBlue = '#2f6bff'
export const chartRed = '#e25c4a'
export const chartAmber = '#c7863a'
