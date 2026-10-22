<script setup lang="ts">
import { computed } from 'vue'
import {
  closeRuleDetail,
  openRuleDetail,
  refreshRuleCenter,
  searchRuleCenter,
  state,
  toggleChat,
  useSuggestion,
} from '../store/workbench'
import type { RuleDetail, RuleSearchItem } from '../types'

const center = computed(() => state.ruleCenter)
const feed = computed(() => state.rules)
const results = computed(() => center.value.results)
const total = computed(() => center.value.total)
const pages = computed(() => Math.max(1, Math.ceil(total.value / center.value.size)))
const detail = computed(() => center.value.detail)
const detailOpen = computed(() => Boolean(detail.value || center.value.detailLoading || center.value.detailError))
const hasActivities = computed(() => Boolean(feed.value?.activities?.length))
const activityEmpty = computed(() => feed.value?.unavailable.find((item) => item.key === 'platform_activity'))
const rulesUnavailable = computed(() => feed.value?.reason === 'RULE_FEED_UNAVAILABLE')
const hasDemoRules = computed(() =>
  Boolean((feed.value?.rules || []).some((rule) => rule.demo) || results.value.some((rule) => rule.demo)),
)
const unavailableItems = computed(() =>
  (feed.value?.unavailable || []).filter((entry) => entry.key !== 'platform_activity'),
)
const refreshing = computed(() => state.rulesLoading || center.value.loading)
const emptyMessage = computed(() => {
  if (center.value.query.trim() || center.value.category) return '没有匹配的规则，试试换关键词或分类。'
  if (rulesUnavailable.value) return '规则服务暂不可用，请稍后点右上角刷新；不会用假条款代替。'
  if (feed.value?.status === 'empty') return '规则库未收录；等待导入含 rule_key / section / effective_date 的真实条款。'
  return '暂无规则数据。'
})

function search(): void {
  void searchRuleCenter(1)
}

function pickCategory(): void {
  void searchRuleCenter(1)
}

function prevPage(): void {
  if (center.value.page > 1) void searchRuleCenter(center.value.page - 1)
}

function nextPage(): void {
  if (center.value.page < pages.value) void searchRuleCenter(center.value.page + 1)
}

function openDetail(rule: RuleSearchItem): void {
  void openRuleDetail(rule)
}

function askRule(rule: RuleSearchItem | RuleDetail): void {
  toggleChat(true)
  useSuggestion(
    `请解释平台规则「${rule.title}」${rule.section ? ` §${rule.section}` : ''}，并说明它对经营的影响。`
    + (rule.demo ? '注意：这是演示条款，不是真实平台政策。' : ''),
  )
}

function refreshAll(): void {
  void refreshRuleCenter()
}
</script>

<template>
  <section class="card rule-card">
    <div class="card-head">
      <div>
        <div class="card-title">平台规则与运营日历</div>
        <div class="card-sub">搜索条款、查看原文；演示语料会明确标注，不伪造真实政策</div>
      </div>
      <div class="card-actions">
        <span class="pill" :class="{ warn: total === 0 || rulesUnavailable }">
          {{ rulesUnavailable ? '规则服务暂不可用' : `${total} 条规则` }}
        </span>
        <span v-if="hasDemoRules" class="pill warn">演示语料</span>
        <span class="pill" :class="{ warn: !hasActivities }">{{ hasActivities ? `${feed?.activities.length} 个活动` : '活动空态' }}</span>
        <button type="button" class="icon-button" title="刷新规则" :disabled="refreshing" @click="refreshAll">
          <svg viewBox="0 0 24 24" aria-hidden="true" :class="{ spin: refreshing }"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v4h-4" /></svg>
        </button>
      </div>
    </div>

    <template v-if="!detailOpen">
      <div class="rule-search">
        <input
          v-model="center.query"
          type="search"
          maxlength="100"
          placeholder="搜索规则标题或条款关键词…"
          aria-label="搜索规则"
          @keyup.enter="search"
        />
        <select v-model="center.category" aria-label="规则分类" @change="pickCategory">
          <option value="">全部分类</option>
          <option v-for="category in center.categories" :key="category.key" :value="category.key">
            {{ category.label }}（{{ category.count }}）
          </option>
        </select>
        <button type="button" class="ghost-button" :disabled="center.loading" @click="search">搜索</button>
      </div>

      <div class="rule-result-meta">
        共 {{ total }} 条 · 第 {{ center.page }} / {{ pages }} 页
        <span v-if="center.loading">· 搜索中…</span>
      </div>

      <div v-if="center.loading && !results.length" class="empty-state rule-empty">正在加载规则…</div>
      <div v-else-if="center.error" class="empty-state rule-empty">
        <div>
          <strong>规则搜索暂不可用</strong>
          {{ center.error }}
        </div>
      </div>
      <div v-else-if="results.length" class="rule-list">
        <button
          v-for="rule in results"
          :key="rule.rule_id + '-' + rule.section"
          type="button"
          class="rule-item"
          @click="openDetail(rule)"
        >
          <span class="rule-title">
            <span>{{ rule.title }}</span>
            <span class="rule-tags">
              <span v-if="rule.demo" class="pill warn">演示</span>
              <span class="tiny mono muted">§{{ rule.section }}</span>
            </span>
          </span>
          <div class="rule-snippet">{{ rule.snippet }}</div>
          <div class="rule-meta tiny muted">
            {{ rule.category || '未分类' }} · 生效 {{ rule.effective_date || '—' }} · {{ rule.source || '规则库' }} · 点击查看原文
          </div>
        </button>
      </div>
      <div v-else class="empty-state rule-empty">
        <div>
          <strong>{{ rulesUnavailable ? '规则服务暂不可用' : (feed?.status === 'empty' ? '规则库未收录' : '没有匹配的规则') }}</strong>
          {{ emptyMessage }}
        </div>
      </div>

      <div v-if="total > center.size" class="rule-pager">
        <button type="button" class="ghost-button" :disabled="center.page <= 1 || center.loading" @click="prevPage">上一页</button>
        <span class="tiny muted">{{ center.page }} / {{ pages }}</span>
        <button type="button" class="ghost-button" :disabled="center.page >= pages || center.loading" @click="nextPage">下一页</button>
      </div>
    </template>

    <div v-else class="rule-detail">
      <button type="button" class="text-button rule-back" @click="closeRuleDetail">← 返回规则列表</button>
      <div v-if="center.detailLoading" class="empty-state rule-empty">正在打开规则…</div>
      <div v-else-if="center.detailError" class="empty-state rule-empty">
        <div>
          <strong>规则详情暂不可用</strong>
          {{ center.detailError }}
        </div>
      </div>
      <template v-else-if="detail">
        <div v-if="detail.demo" class="demo-banner">演示规则，不是真实平台政策；仅用于验证规则检索与引用链路。</div>
        <h3 class="rule-detail-title">{{ detail.title }}</h3>
        <div class="rule-detail-meta">
          §{{ detail.section }} · {{ detail.category || '未分类' }} · 生效 {{ detail.effective_date || '—' }} · {{ detail.source || '规则库' }}
        </div>
        <p class="rule-content">{{ detail.content || detail.snippet }}</p>
        <div class="rule-actions">
          <button type="button" class="primary-button" @click="askRule(detail)">问 AI 这条规则</button>
          <button type="button" class="ghost-button" @click="closeRuleDetail">返回列表</button>
        </div>
      </template>
    </div>

    <template v-if="!detailOpen">
      <div class="activity-block">
        <div class="section-label">平台活动</div>
        <div v-if="hasActivities" class="activity-list">
          <div v-for="item in feed?.activities" :key="item.activity_key" class="activity-item">
            <div class="rule-title">
              <span>{{ item.title }}</span>
              <span class="tiny mono muted">{{ item.start_date }} ~ {{ item.end_date }}</span>
            </div>
            <div class="rule-snippet">{{ item.description }}</div>
            <div class="tiny muted">{{ item.source }}</div>
          </div>
        </div>
        <div v-else class="activity-empty tiny muted">
          {{ activityEmpty?.message || '暂无活动数据源' }}
        </div>
      </div>

      <div class="rule-bottom" :class="{ 'rule-bottom-single': !unavailableItems.length }">
        <div>
          <div class="section-label">运营日历</div>
          <div v-for="item in feed?.calendar || []" :key="`${item.name}-${item.date}`" class="calendar-row">
            <span class="calendar-date">{{ item.date }}</span>
            <span>{{ item.name }}</span>
            <span class="tiny muted">{{ item.type }} · 影响 {{ item.impact }}</span>
          </div>
          <div v-if="!feed?.calendar?.length" class="tiny muted">暂无日历数据。</div>
        </div>
        <div v-if="unavailableItems.length" class="rule-unavailable">
          <div class="section-label">暂不可用</div>
          <div v-for="item in unavailableItems" :key="item.key" class="unavailable-row">
            <span class="pill">{{ item.key }}</span>
            <span class="tiny muted">{{ item.message }}</span>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.rule-card { scroll-margin-top: 86px; }
.rule-meta { margin-top: 6px; }
.rule-search { display: flex; gap: 8px; margin-bottom: 9px; }
.rule-search input { flex: 1; min-width: 0; padding: 8px 10px; border: 1px solid var(--line); border-radius: 10px; background: #fff; color: var(--ink); font-size: 12px; }
.rule-search input:focus { outline: 2px solid var(--blue-soft); border-color: rgba(47, 107, 255, .45); }
.rule-search select { max-width: 150px; padding: 8px 9px; border: 1px solid var(--line); border-radius: 10px; background: #fff; color: var(--ink); font-size: 11px; }
.rule-result-meta { margin-bottom: 8px; color: var(--faint); font-size: 10px; }
.rule-tags { display: inline-flex; align-items: center; gap: 6px; flex: 0 0 auto; }
.rule-pager { display: flex; align-items: center; justify-content: flex-end; gap: 8px; margin-top: 10px; }
.rule-back { margin-bottom: 10px; }
.rule-detail-title { margin: 0 0 5px; font-size: 17px; line-height: 1.45; letter-spacing: -.02em; }
.rule-detail-meta { margin-bottom: 12px; color: var(--muted); font-size: 11px; }
.rule-content { margin: 0; padding: 12px 14px; border: 1px solid var(--line); border-radius: 12px; background: var(--paper); color: var(--ink); font-size: 13px; line-height: 1.85; white-space: pre-wrap; }
.rule-actions { display: flex; gap: 8px; margin-top: 12px; }
.demo-banner { margin-bottom: 10px; padding: 8px 10px; border: 1px solid rgba(199, 134, 58, .25); border-radius: 10px; background: var(--amber-soft); color: #7b4f16; font-size: 11px; line-height: 1.55; }
.activity-block { margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--line); }
.activity-list { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
.activity-item { padding: 10px 11px; border: 1px solid rgba(47, 107, 255, .16); border-radius: 12px; background: #f8faff; }
.activity-empty { padding: 10px 12px; border: 1px dashed var(--line-strong); border-radius: 10px; }
.rule-bottom { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 14px; padding-top: 14px; border-top: 1px dashed var(--line); }
.rule-bottom.rule-bottom-single { grid-template-columns: 1fr; }
.section-label { margin-bottom: 6px; color: var(--faint); font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.unavailable-row { display: flex; align-items: flex-start; gap: 7px; margin-bottom: 7px; }
.rule-empty { min-height: 150px; }
@media (max-width: 700px) {
  .rule-bottom, .activity-list { grid-template-columns: 1fr; }
  .rule-search { flex-wrap: wrap; }
  .rule-search select { flex: 1; max-width: none; }
}
</style>
