<script setup lang="ts">
import { onMounted } from 'vue'
import AiBrief from './components/AiBrief.vue'
import AnomalyStrip from './components/AnomalyStrip.vue'
import ChatDock from './components/ChatDock.vue'
import DishRank from './components/DishRank.vue'
import Heatmap from './components/Heatmap.vue'
import KpiGrid from './components/KpiGrid.vue'
import PreferencePanel from './components/PreferencePanel.vue'
import RefundChart from './components/RefundChart.vue'
import RuleFeed from './components/RuleFeed.vue'
import TrendChart from './components/TrendChart.vue'
import {
  loadDashboard,
  loadRuleCenter,
  loadSidecars,
  rangeOptions,
  setRange,
  state,
  toggleChat,
} from './store/workbench'

onMounted(() => {
  void loadDashboard()
  void loadSidecars()
  void loadRuleCenter()
})

function scrollTo(id: string): void {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function refresh(): void {
  void loadDashboard(true)
}
</script>

<template>
  <div class="app-shell">
    <aside class="rail" aria-label="主导航">
      <div class="rail-brand" title="苍穹外卖 · AI 经营工作台">
        <span class="brand-mark">S</span>
      </div>
      <nav class="rail-nav">
        <button class="rail-button active" type="button" title="经营看板" @click="scrollTo('dashboard-top')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /></svg>
        </button>
        <button class="rail-button" type="button" title="规则与日历" @click="scrollTo('rules-section')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5M9 13h7M9 17h7" /></svg>
        </button>
        <button class="rail-button" type="button" title="推送偏好" @click="scrollTo('preferences-section')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" /><circle cx="12" cy="12" r="3.5" /></svg>
        </button>
      </nav>
      <div class="rail-spacer" />
      <button class="rail-ai" type="button" title="问 AI" @click="toggleChat(true)">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /></svg>
        <span>AI</span>
      </button>
      <div class="rail-avatar" title="商家账号">商</div>
    </aside>

    <div class="shell">
      <header class="topbar">
        <div class="crumb">
          <span class="crumb-home">苍穹外卖</span>
          <span class="crumb-sep">/</span>
          <strong>AI 经营工作台</strong>
          <span class="store-badge">商家级</span>
        </div>
        <div class="topbar-actions">
          <span class="data-asof">
            <span class="dot" :class="{ warn: state.plan?.data_status?.gap || !!state.error }" />
            <template v-if="state.plan">
              数据截至 {{ state.plan.data_status.latest_data_date || '暂无' }}
            </template>
            <template v-else-if="state.error">数据暂不可用</template>
            <template v-else>加载中…</template>
          </span>
          <div class="segmented" role="tablist" aria-label="日期区间">
            <button
              v-for="option in rangeOptions"
              :key="option.key"
              type="button"
              class="seg"
              :class="{ active: state.range === option.key }"
              role="tab"
              :aria-selected="state.range === option.key"
              @click="setRange(option.key)"
            >
              {{ option.label }}
            </button>
          </div>
          <button class="ghost-button" type="button" :disabled="state.loading" @click="refresh">
            <svg viewBox="0 0 24 24" aria-hidden="true" :class="{ spin: state.loading }"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v4h-4" /></svg>
            刷新
          </button>
          <button class="primary-button" type="button" @click="toggleChat(true)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H9l-4 4z" /></svg>
            问 AI
          </button>
        </div>
      </header>

      <main id="dashboard-top" class="page" :aria-busy="state.loading">
        <section v-if="state.error && !state.plan" class="state-panel" role="alert">
          <span class="state-icon">!</span>
          <div class="state-copy">
            <strong>{{ state.error }}</strong>
            <p>
              {{ state.error.indexOf('数据库') >= 0
                ? '数据库不可用不等于没有数据；页面不会用 0 或演示数据替代真实结果。'
                : '请确认后端服务可用后重试；页面不会静默使用旧快照。' }}
            </p>
          </div>
          <button class="primary-button" type="button" @click="refresh">重试</button>
        </section>

        <template v-else>
          <div v-if="state.error" class="banner banner-warn" role="alert">
            <strong>{{ state.demo ? '后端未连接，当前为演示数据' : '看板请求失败' }}</strong>
            <span>{{ state.error }}</span>
            <button type="button" class="text-button" @click="refresh">重试</button>
          </div>

          <AiBrief />

          <AnomalyStrip />

          <div class="dashboard-grid">
            <KpiGrid class="col-12" />
            <TrendChart class="col-8" />
            <DishRank class="col-4" />
            <RefundChart class="col-6" />
            <Heatmap class="col-6" />
            <RuleFeed id="rules-section" class="col-7" />
            <PreferencePanel id="preferences-section" class="col-5" />
          </div>
        </template>

        <footer class="page-foot">
          <span>数据口径：完成订单 status=5；退款为整单近似。</span>
          <span>Java 平台只读 · Agent 服务 {{ state.demo ? '演示模式' : (state.error ? '服务异常' : '已连接') }}</span>
          <span v-if="state.lastLoadedAt">最近加载 {{ state.lastLoadedAt }}</span>
        </footer>
      </main>
    </div>

    <ChatDock />
    <div v-if="state.toast" class="toast" role="status">{{ state.toast }}</div>
  </div>
</template>
