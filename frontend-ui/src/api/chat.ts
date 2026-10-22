import type { WidgetContext } from '../types'
import { API_BASE, TOKEN } from './http'

export interface StreamHandlers {
  onEvent: (event: string, data: Record<string, unknown>, id?: string) => void
  onError: (error: Error) => void
  onClose: () => void
}

export interface StreamPayload {
  message: string
  sessionId: string
  widgetContext?: WidgetContext | null
}

interface ParsedBlock {
  event: string
  data: string
  id?: string
}

function parseBlock(block: string): ParsedBlock | null {
  let event = 'message'
  let data = ''
  let id: string | undefined
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) continue
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
    else if (line.startsWith('id:')) id = line.slice(3).trim()
  }
  return data ? { event, data, id } : null
}

export async function streamChat(
  payload: StreamPayload,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`

  const body: Record<string, unknown> = {
    message: payload.message,
    session_id: payload.sessionId,
  }
  if (payload.widgetContext) body.widget_context = payload.widgetContext

  const response = await fetch(`${API_BASE}/api/agent/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error(`对话服务不可用（${response.status}）`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let stalled = false
  let stallTimer: number | undefined
  const STALL_MS = 45000
  const armWatchdog = (): void => {
    if (stallTimer) window.clearTimeout(stallTimer)
    stallTimer = window.setTimeout(() => {
      stalled = true
      void reader.cancel()
    }, STALL_MS)
  }
  armWatchdog()

  const flushBlock = (block: string) => {
    const parsed = parseBlock(block)
    if (!parsed) return
    let data: Record<string, unknown> = {}
    try {
      data = JSON.parse(parsed.data) as Record<string, unknown>
    } catch {
      data = { raw: parsed.data }
    }
    handlers.onEvent(parsed.event, data, parsed.id)
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      armWatchdog()
      buffer += decoder.decode(value, { stream: true })
      let index = buffer.indexOf('\n\n')
      while (index >= 0) {
        const block = buffer.slice(0, index)
        buffer = buffer.slice(index + 2)
        flushBlock(block)
        index = buffer.indexOf('\n\n')
      }
    }
    if (stalled) {
      handlers.onError(new Error('对话连接超过 45 秒没有新数据，已停止；可以重试。'))
    } else if (buffer.trim()) {
      flushBlock(buffer)
    }
  } catch (error) {
    if (stalled) {
      handlers.onError(new Error('对话连接超过 45 秒没有新数据，已停止；可以重试。'))
    } else if ((error as Error).name !== 'AbortError') {
      handlers.onError(error as Error)
    }
  } finally {
    if (stallTimer) window.clearTimeout(stallTimer)
    handlers.onClose()
  }
}
