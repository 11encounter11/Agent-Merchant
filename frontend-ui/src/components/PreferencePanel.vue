<script setup lang="ts">
import { reactive } from 'vue'
import { addPreference, notify, removePreference, state, toggleChat, useSuggestion } from '../store/workbench'
import type { RangeKey } from '../types'

const metrics = [
  { value: 'revenue', label: '销售额' },
  { value: 'orders', label: '订单量' },
  { value: 'aov', label: '客单价' },
  { value: 'refund_rate', label: '退款率' },
  { value: 'new_customers', label: '新客' },
  { value: 'dish_sales', label: '菜品销量' },
  { value: 'order_heatmap', label: '时段热力' },
]
const charts = [
  { value: 'line', label: '折线图' },
  { value: 'bar', label: '柱状图' },
  { value: 'heatmap', label: '热力图' },
  { value: 'table', label: '表格' },
  { value: 'kpi', label: '数字卡片' },
]
const cadences = [
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每周' },
  { value: 'manual', label: '手动' },
]
const ranges: Array<{ value: RangeKey; label: string }> = [
  { value: 'yesterday', label: '昨日' },
  { value: 'last7', label: '近 7 日' },
  { value: 'last30', label: '近 30 日' },
  { value: 'this_week', label: '本周' },
  { value: 'this_month', label: '本月' },
]

const form = reactive({
  metric: 'refund_rate',
  chart_type: 'line',
  cadence: 'daily',
  range_key: 'yesterday' as RangeKey,
})

function submit(): void {
  if (!state.plan) {
    notify('看板尚未加载，稍后再试')
    return
  }
  void addPreference({ ...form })
}

function askAi(): void {
  toggleChat(true)
  useSuggestion('以后每天给我看退款趋势，用折线图。')
}
</script>

<template>
  <section class="card preference-card">
    <div class="card-head">
      <div>
        <div class="card-title">AI 看板编排</div>
        <div class="card-sub">保存后，下次打开工作台会按偏好重新排序看板</div>
      </div>
      <span class="pill info">{{ state.preferences.length }} 项偏好</span>
    </div>

    <div v-if="state.preferences.length" class="pref-list">
      <div v-for="pref in state.preferences" :key="pref.id" class="pref-item">
        <div>
          <div class="pref-title">{{ pref.title }}</div>
          <div class="pref-meta">{{ pref.metric }} · {{ pref.chart_type }} · {{ pref.cadence }} · {{ pref.range_key }}</div>
        </div>
        <button type="button" class="icon-button" title="删除偏好" @click="removePreference(pref.id)">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V5h6v2M7 7l1 13h8l1-13M10 11v5M14 11v5" /></svg>
        </button>
      </div>
    </div>
    <div v-else class="empty-state pref-empty">
      <div>
        <strong>还没有推送偏好</strong>
        可以对 AI 说“以后每天给我看退款趋势”，或在这里手动添加。
      </div>
    </div>

    <div class="pref-form">
      <select v-model="form.metric" aria-label="指标">
        <option v-for="item in metrics" :key="item.value" :value="item.value">{{ item.label }}</option>
      </select>
      <select v-model="form.chart_type" aria-label="图表类型">
        <option v-for="item in charts" :key="item.value" :value="item.value">{{ item.label }}</option>
      </select>
      <select v-model="form.cadence" aria-label="推送频率">
        <option v-for="item in cadences" :key="item.value" :value="item.value">{{ item.label }}</option>
      </select>
      <select v-model="form.range_key" aria-label="数据区间">
        <option v-for="item in ranges" :key="item.value" :value="item.value">{{ item.label }}</option>
      </select>
      <button type="button" class="primary-button wide" @click="submit">保存到下次看板</button>
    </div>
    <p class="form-note">
      也可以在对话里直接说。例如：“以后每天给我看退款趋势，用折线图。”
      <button type="button" class="text-button" @click="askAi">让 AI 记住</button>
    </p>
  </section>
</template>

<style scoped>
.preference-card { display: flex; flex-direction: column; }
.pref-empty { min-height: 120px; margin-bottom: 4px; }
.pref-form .wide { width: 100%; justify-content: center; }
</style>
