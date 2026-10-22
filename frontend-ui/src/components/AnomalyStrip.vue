<script setup lang="ts">
import { computed } from 'vue'
import { selectWidget, state, useSuggestion } from '../store/workbench'
import type { Anomaly } from '../types'

const anomalies = computed(() => state.plan?.anomalies || [])

function widgetId(anomaly: Anomaly): string {
  return anomaly.type === 'refund_spike' ? 'refund_trend' : 'sales_trend'
}

function ask(anomaly: Anomaly): void {
  selectWidget(widgetId(anomaly), anomaly.selection || {}, anomaly.title)
  useSuggestion(`请解释这个异常：${anomaly.title}。${anomaly.detail}`)
}
</script>

<template>
  <section v-if="anomalies.length" class="anomaly-strip" aria-label="异常提示">
    <div class="anomaly-head">
      <span class="pill danger">异常提示</span>
      <span class="tiny muted">{{ anomalies.length }} 条 · 来自当前看板快照</span>
    </div>
    <div class="anomaly-list">
      <article
        v-for="item in anomalies.slice(0, 3)"
        :key="item.type + item.date"
        class="anomaly-item"
        :class="item.severity"
      >
        <div class="anomaly-copy">
          <strong>{{ item.title }}</strong>
          <span>{{ item.detail }}</span>
          <small>{{ item.date }}</small>
        </div>
        <button type="button" class="ghost-button" @click="ask(item)">问 AI</button>
      </article>
    </div>
  </section>
</template>

<style scoped>
.anomaly-strip { margin-top: 16px; padding: 14px 16px; border: 1px solid rgba(226, 92, 74, .2); border-radius: 16px; background: #fff7f4; }
.anomaly-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.anomaly-list { display: grid; gap: 8px; }
.anomaly-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 10px; border: 1px solid rgba(226, 92, 74, .16); border-radius: 11px; background: #fff; }
.anomaly-item.high { border-left: 3px solid var(--red); }
.anomaly-item.medium { border-left: 3px solid var(--amber); }
.anomaly-copy { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.anomaly-copy strong { font-size: 13px; }
.anomaly-copy span { color: var(--muted); font-size: 12px; line-height: 1.55; }
.anomaly-copy small { color: var(--faint); font-family: var(--mono); font-size: 10px; }
@media (max-width: 700px) {
  .anomaly-item { align-items: flex-start; flex-direction: column; }
}
</style>
