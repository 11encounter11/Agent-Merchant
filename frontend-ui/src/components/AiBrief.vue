<script setup lang="ts">
import { computed } from 'vue'
import { state, toggleChat, useSuggestion } from '../store/workbench'

const plan = computed(() => state.plan)
const status = computed(() => plan.value?.data_status)
const hasFallback = computed(() => Boolean(status.value?.fallback_reason))
const fallbackIsGap = computed(() => status.value?.fallback_reason === 'NO_DATA_IN_REQUESTED_WINDOW')
const noData = computed(() => status.value?.fallback_reason === 'NO_DATA_AT_ALL')

const headline = computed(() => {
  if (!plan.value) return '正在读取经营数据…'
  if (noData.value) return '平台还没有可用的经营数据'
  if (fallbackIsGap.value) return `${plan.value.range.label}没有支付订单，先看最近 7 个完整日`
  return `这是你${plan.value.range.label}的经营快照`
})

const effectiveRange = computed(() => {
  if (!status.value) return ''
  return `${status.value.effective_start} 至 ${status.value.effective_end}（开区间）`
})

function ask(question: string): void {
  toggleChat(true)
  useSuggestion(question)
}
</script>

<template>
  <section v-if="plan" class="brief" aria-labelledby="brief-title">
    <div class="brief-top">
      <div class="brief-main">
        <div class="brief-kicker">
          <span class="kicker-line" />
          AI 编排 · {{ plan.range.label }}
        </div>
        <h1 id="brief-title" class="brief-title">{{ headline }}</h1>
        <p class="brief-copy">{{ plan.ai_brief.text }}</p>
        <div class="brief-meta">
          <span class="pill info">有效区间 {{ effectiveRange }}</span>
          <span v-if="hasFallback" class="pill warn">
            {{ fallbackIsGap ? '请求区间无支付订单，已自动回退' : '暂无任何经营数据' }}
          </span>
          <span v-if="status?.refund_approximation" class="pill">退款为整单近似</span>
          <span v-if="!status?.store_dimension" class="pill">商家级 · 无门店维度</span>
        </div>
        <div class="brief-questions">
          <button
            v-for="question in plan.ai_brief.suggested_questions"
            :key="question"
            type="button"
            class="question-chip"
            @click="ask(question)"
          >
            {{ question }}
          </button>
        </div>
      </div>
      <div class="brief-side">
        <strong>{{ plan.widgets.length }}</strong>
        <span>个 AI 看板模块</span>
        <span class="pill" :class="{ warn: plan.partial }">{{ plan.partial ? '部分查询失败' : '数据完整' }}</span>
        <button type="button" class="ghost-button" @click="toggleChat(true)">继续追问</button>
      </div>
    </div>
  </section>
  <section v-else class="brief brief-skeleton" aria-busy="true">
    <div class="skeleton-line wide" />
    <div class="skeleton-line" />
    <div class="skeleton-line short" />
  </section>
</template>

<style scoped>
.brief-main { flex: 1; min-width: 0; }
.kicker-line { width: 22px; height: 2px; border-radius: 2px; background: var(--blue); }
.brief-skeleton { min-height: 180px; }
.skeleton-line { height: 12px; width: 46%; margin: 10px 0; border-radius: 8px; background: linear-gradient(90deg, #ebe9e2, #f7f6f1, #ebe9e2); background-size: 200% 100%; animation: shimmer 1.4s infinite linear; }
.skeleton-line.wide { width: 78%; height: 22px; }
.skeleton-line.short { width: 28%; }
@keyframes shimmer { to { background-position: -200% 0; } }
</style>
