<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  clearContext,
  resetSession,
  retryLast,
  sendMessage,
  state,
  stopStreaming,
  toggleChat,
  useSuggestion,
} from '../store/workbench'
import type { ChatCitation, ChatMessage, MessagePart } from '../types'
import { renderMarkdown } from '../lib/markdown'

const scroller = ref<HTMLDivElement | null>(null)
const context = computed(() => state.context)
const hasMessages = computed(() => state.messages.length > 0)
const canSend = computed(() => state.composerText.trim().length > 0 && !state.streaming)
const canRetry = computed(() => {
  if (state.streaming) return false
  const last = state.messages[state.messages.length - 1]
  if (!last || last.role !== 'assistant') return false
  return last.parts.some((part) => part.type === 'note' && part.tone === 'warn')
})

watch(
  () => [state.messages.length, state.messages[state.messages.length - 1]?.parts.length],
  async () => {
    await nextTick()
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
  },
  { deep: true },
)

function send(): void {
  if (!canSend.value) return
  void sendMessage(state.composerText)
}

function quick(text: string): void {
  useSuggestion(text)
}

function partKey(message: ChatMessage, part: MessagePart, index: number): string {
  if (part.type === 'citation') return `${message.id}-c-${part.citation.rule_id}-${part.citation.section}-${index}`
  if (part.type === 'tool') return `${message.id}-t-${part.name}-${index}`
  return `${message.id}-${index}`
}

function roleLabel(message: ChatMessage): string {
  return message.role === 'user' ? '你' : 'AI 顾问'
}

function isRuleCitation(citation: ChatCitation): boolean {
  return Boolean(citation.rule_id && (citation.section || citation.effective_date))
}
</script>

<template>
  <button v-if="!state.chatOpen" type="button" class="chat-fab" @click="toggleChat(true)">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H9l-4 4z" /><path d="M8 9h8M8 12h5" /></svg>
    问 AI
    <span v-if="state.streaming" class="fab-dot" />
  </button>

  <aside v-else class="chat-dock" aria-label="AI 经营顾问对话">
    <header class="chat-head">
      <div class="chat-title">
        <span class="ai-orb">AI</span>
        <div>
          <strong>经营顾问</strong>
          <span class="chat-sub">{{ state.streaming ? '正在分析…' : '数据 + 规则 + 策略' }}</span>
        </div>
      </div>
      <div class="chat-head-actions">
        <button type="button" class="icon-button" title="新会话" @click="resetSession">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
        </button>
        <button type="button" class="icon-button" title="关闭" @click="toggleChat(false)">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>
    </header>

    <div v-if="context" class="context-chip">
      <div class="context-copy">
        <span class="context-kicker">图表上下文</span>
        <strong>{{ context.title }}</strong>
        <span class="tiny muted">{{ Object.entries(context.selection).map(([key, value]) => `${key}=${value}`).join(' · ') }}</span>
        <span class="tiny muted">区间 {{ context.range_key }} · 快照 {{ context.snapshot_id.slice(0, 10) }}…</span>
      </div>
      <button type="button" class="icon-button" title="移除上下文" @click="clearContext">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
      </button>
    </div>

    <div ref="scroller" class="chat-messages" aria-live="polite">
      <div v-if="!hasMessages" class="chat-welcome">
        <div class="welcome-title">从一张图开始问</div>
        <p>点击看板里的任一天、菜或时段，再补一句问题。也可以直接让我记住下次要看什么。</p>
        <div class="welcome-questions">
          <button type="button" @click="quick('为什么最近销售额下降？哪些菜拖累？')">为什么最近销售额下降？</button>
          <button type="button" @click="quick('退款率正常吗？平台退款规则怎么规定？')">退款率正常吗？</button>
          <button type="button" @click="quick('以后每天给我看退款趋势，用折线图。')">以后每天给我看退款趋势</button>
        </div>
      </div>

      <article v-for="message in state.messages" :key="message.id" class="message" :class="message.role">
        <div class="message-meta">
          <span>{{ roleLabel(message) }}</span>
          <span>{{ message.time }}</span>
        </div>
        <div class="message-body">
          <template v-for="(part, index) in message.parts" :key="partKey(message, part, index)">
            <template v-if="part.type === 'text'">
              <div v-if="message.role === 'assistant'" class="msg-text markdown" v-html="renderMarkdown(part.text)" />
              <div v-else class="msg-text">{{ part.text }}</div>
            </template>
            <div v-else-if="part.type === 'tool'" class="tool-chip" :class="part.status">
              <span class="tool-dot" />
              <span>{{ part.name }}</span>
              <span class="tiny muted">{{ part.status === 'running' ? '执行中' : '完成' }}</span>
            </div>
            <div v-else-if="part.type === 'citation'" class="citation-card">
              <div class="citation-head">
                <span class="pill" :class="{ info: isRuleCitation(part.citation) }">
                  {{ isRuleCitation(part.citation) ? '规则引用' : '参考来源' }}
                </span>
                <span v-if="part.citation.demo" class="pill warn">演示</span>
                <span v-if="isRuleCitation(part.citation) && part.citation.section" class="tiny muted">§ {{ part.citation.section }}</span>
                <span v-else-if="!isRuleCitation(part.citation)" class="tiny muted">{{ part.citation.source || '知识库' }}</span>
                <span v-else class="tiny muted">规则</span>
              </div>
              <strong>{{ part.citation.title }}</strong>
              <div v-if="part.citation.snippet" class="citation-snippet">{{ part.citation.snippet }}</div>
              <div class="tiny muted">
                <template v-if="part.citation.effective_date">生效 {{ part.citation.effective_date }}</template>
                <template v-else-if="part.citation.source">{{ part.citation.source }}</template>
                <template v-else>服务端未返回来源字段</template>
              </div>
            </div>
            <div v-else-if="part.type === 'usage'" class="usage-chip">
              本轮 {{ part.totalTokens.toLocaleString('zh-CN') }} tokens
            </div>
            <div v-else-if="part.type === 'note'" class="msg-note" :class="part.tone || 'info'">
              {{ part.text }}
            </div>
          </template>
          <span v-if="state.streaming && message === state.messages[state.messages.length - 1]" class="typing-cursor" />
        </div>
      </article>
    </div>

    <footer class="chat-composer">
      <div class="quick-commands">
        <button type="button" @click="quick('以后每天给我看退款趋势，用折线图。')">记住：每天退款趋势</button>
        <button type="button" @click="quick('取消每天退款图。')">取消退款偏好</button>
      </div>
      <div v-if="canRetry" class="retry-row">
        <button type="button" class="retry-button" @click="retryLast">重试上一轮</button>
      </div>
      <div class="composer-box">
        <textarea
          v-model="state.composerText"
          rows="2"
          placeholder="例如：为什么 7 月 26 日卖得好？哪些菜拖累客单价？"
          aria-label="输入经营问题"
          @keydown.enter.exact.prevent="send"
        />
        <button v-if="!state.streaming" type="button" class="send-button" :disabled="!canSend" @click="send">
          发送
        </button>
        <button v-else type="button" class="send-button stop" @click="stopStreaming">停止</button>
      </div>
      <p class="composer-note">回答会引用当前看板区间；数值与规则以服务端查询为准。</p>
    </footer>
  </aside>
</template>

<style scoped>
.chat-fab {
  position: fixed; right: 24px; bottom: 24px; z-index: 40;
  display: inline-flex; align-items: center; gap: 8px; padding: 12px 17px;
  border: 1px solid rgba(255,255,255,.15); border-radius: 999px;
  background: var(--navy); color: #fff; font-size: 13px; font-weight: 600;
  box-shadow: 0 16px 34px rgba(17,27,43,.25);
}
.chat-fab:hover { background: #1c2c44; }
.fab-dot { width: 7px; height: 7px; border-radius: 50%; background: #7ca3ff; animation: pulse 1.2s infinite; }
@keyframes pulse { 50% { opacity: .35; } }
.chat-dock {
  position: fixed; top: 16px; right: 16px; bottom: 16px; z-index: 50;
  display: flex; flex-direction: column; width: 424px; max-width: calc(100vw - 32px);
  border: 1px solid var(--line); border-radius: 22px; background: #fbfaf7;
  box-shadow: 0 24px 70px rgba(17,27,43,.24); overflow: hidden;
}
.chat-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--line); background: rgba(255,255,255,.8); }
.chat-title { display: flex; align-items: center; gap: 10px; }
.ai-orb { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 12px; background: linear-gradient(135deg, #2f6bff, #7ca3ff); color: #fff; font-size: 11px; font-weight: 800; letter-spacing: .04em; }
.chat-title strong { display: block; font-size: 13px; }
.chat-sub { display: block; margin-top: 2px; color: var(--muted); font-size: 11px; }
.chat-head-actions { display: flex; gap: 6px; }
.context-chip { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin: 10px 14px 0; padding: 10px 11px; border: 1px solid rgba(47,107,255,.2); border-radius: 13px; background: var(--blue-soft); }
.context-copy { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.context-kicker { color: #2454c8; font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.context-copy strong { font-size: 12px; }
.chat-messages { flex: 1; overflow-y: auto; padding: 14px; scroll-behavior: smooth; }
.chat-welcome { padding: 16px 6px; }
.welcome-title { font-size: 16px; font-weight: 700; letter-spacing: -.02em; }
.chat-welcome p { margin: 8px 0 14px; color: var(--muted); font-size: 12px; line-height: 1.7; }
.welcome-questions { display: flex; flex-direction: column; gap: 7px; }
.welcome-questions button { padding: 9px 11px; border: 1px solid var(--line); border-radius: 10px; background: #fff; color: var(--ink); text-align: left; font-size: 12px; }
.welcome-questions button:hover { border-color: rgba(47,107,255,.3); background: #fbfcff; }
.message { margin-bottom: 14px; }
.message-meta { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 4px; color: var(--faint); font-size: 10px; }
.message.user .message-meta { justify-content: flex-end; }
.message-body { display: flex; flex-direction: column; gap: 7px; }
.message.user .message-body { align-items: flex-end; }
.msg-text { margin: 0; max-width: 100%; padding: 10px 12px; border-radius: 13px; background: #fff; border: 1px solid var(--line); font-size: 13px; line-height: 1.7; white-space: pre-wrap; }
.msg-text.markdown { white-space: normal; }
.msg-text.markdown :deep(p) { margin: 0 0 8px; }
.msg-text.markdown :deep(p:last-child) { margin-bottom: 0; }
.msg-text.markdown :deep(h1), .msg-text.markdown :deep(h2), .msg-text.markdown :deep(h3), .msg-text.markdown :deep(h4) { margin: 8px 0 4px; font-size: 14px; line-height: 1.5; }
.msg-text.markdown :deep(h1) { font-size: 16px; }
.msg-text.markdown :deep(ul), .msg-text.markdown :deep(ol) { margin: 4px 0; padding-left: 18px; }
.msg-text.markdown :deep(li) { margin: 2px 0; }
.msg-text.markdown :deep(strong) { color: var(--ink); }
.msg-text.markdown :deep(code) { padding: 1px 4px; border-radius: 4px; background: var(--paper); font-family: var(--mono); font-size: 11px; }
.msg-text.markdown :deep(pre) { overflow-x: auto; padding: 10px; border-radius: 10px; background: var(--navy); color: #fff; }
.msg-text.markdown :deep(a) { color: var(--blue); text-decoration: underline; text-underline-offset: 2px; }
.msg-text.markdown :deep(blockquote) { margin: 6px 0; padding-left: 10px; border-left: 2px solid var(--line-strong); color: var(--muted); }
.message.user .msg-text { background: var(--navy); border-color: var(--navy); color: #fff; }
.msg-note { padding: 8px 10px; border-radius: 10px; font-size: 11px; line-height: 1.6; }
.msg-note.info { background: var(--blue-soft); color: #2454c8; }
.msg-note.warn { background: var(--amber-soft); color: #7b4f16; }
.tool-chip { display: inline-flex; align-items: center; gap: 6px; align-self: flex-start; padding: 6px 9px; border: 1px dashed var(--line-strong); border-radius: 9px; background: #fff; color: var(--muted); font-size: 11px; }
.tool-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--amber); }
.tool-chip.success .tool-dot { background: var(--green); }
.usage-chip { align-self: flex-start; padding: 3px 7px; border-radius: 999px; background: var(--paper); color: var(--faint); font-family: var(--mono); font-size: 10px; }
.citation-card { padding: 10px 11px; border: 1px solid var(--line); border-radius: 12px; background: #fff; }
.citation-head { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 5px; }
.citation-card strong { display: block; font-size: 12px; }
.citation-snippet { margin: 5px 0 6px; color: var(--muted); font-size: 11px; line-height: 1.55; }
.typing-cursor { display: inline-block; width: 7px; height: 14px; margin-left: 2px; background: var(--blue); animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }
.chat-composer { padding: 10px 14px 12px; border-top: 1px solid var(--line); background: rgba(255,255,255,.75); }
.quick-commands { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 7px; }
.quick-commands button { flex: 0 0 auto; padding: 4px 8px; border: 1px solid var(--line); border-radius: 999px; background: #fff; color: var(--muted); font-size: 10px; }
.quick-commands button:hover { color: var(--blue); border-color: rgba(47,107,255,.3); }
.retry-row { display: flex; justify-content: flex-end; padding-bottom: 7px; }
.retry-button { padding: 4px 9px; border: 1px solid rgba(226, 92, 74, .3); border-radius: 999px; background: var(--red-soft); color: #a43a2c; font-size: 10px; }
.retry-button:hover { border-color: rgba(226, 92, 74, .5); }
.composer-box { display: flex; align-items: flex-end; gap: 8px; padding: 8px; border: 1px solid var(--line-strong); border-radius: 14px; background: #fff; }
.composer-box textarea { flex: 1; min-height: 42px; max-height: 120px; resize: vertical; border: 0; outline: none; background: transparent; font-size: 13px; line-height: 1.55; }
.send-button { padding: 8px 12px; border: 0; border-radius: 10px; background: var(--navy); color: #fff; font-size: 12px; }
.send-button:disabled { opacity: .45; }
.send-button.stop { background: var(--red); }
.composer-note { margin: 6px 2px 0; color: var(--faint); font-size: 10px; }
@media (max-width: 1100px) {
  .chat-dock { inset: 0; width: auto; max-width: none; border-radius: 0; }
  .chat-fab { right: 16px; bottom: 16px; }
}
</style>
