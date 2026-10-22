"""
Agent 对外服务（Service）

做什么：
- chat() / chat_stream()：限流 → 上下文 → LangGraph → 会话/日志落盘
- thread_id + Checkpointer 续跑

不做什么：
- 不定义图 / 节点

落盘原则（B7）：
- 无论成功、失败还是客户端中途断开，一轮对话都要留痕：
  会话文件 + agent_chat_log（human/ai 两条），否则「谁在什么时候问了什么」
  没有任何权威记录，失败样本也无法回收进评测集。
- 成本口径（token_total）在流式与非流式两条路径上都要写。
"""

import uuid
import logging

from langchain_core.messages import AIMessage, ToolMessage

from agent.graph import get_agent_graph
from agent.checkpointing import thread_config, resume_if_pending
from agent.llm import inspect_turn
from agent.memory.session_memory import session_memory
from agent.memory.context_builder import ContextBuilder
from agent.memory.rate_limit import check_rate_limit
from agent.knowledge.knowledge_base import knowledge_base, compact_hits
from agent.messages import is_placeholder_content
from agent.workbench.planner import validate_widget_context
from agent.workbench.preferences import apply_preference_intent, detect_preference_intent
from db.chat_log import append_chat_log

logger = logging.getLogger(__name__)

_context_builder = ContextBuilder(knowledge_base=knowledge_base)


def _run_config(thread_id: str, session_id: str, turn: dict | None = None) -> dict:
    """图运行配置：checkpoint thread + Langfuse session/tags。

    turn 由调用方用 inspect_turn 算一次后传入：同一次请求里重复做感知/意图
    分类既浪费也会漂移（Langfuse 标签与实际路由对不上就没法按意图归因）。
    """
    tags = ["sky-agent"]
    extra = {}
    if turn:
        intent = (turn.get("intent") or {}).get("intent") or "unknown"
        tier = turn.get("llm_tier") or "large"
        tags.extend([intent, tier])
        extra = {"intent": intent, "llm_tier": tier}
    return thread_config(
        thread_id,
        session_id=session_id,
        tags=tags,
        metadata=extra,
    )


def _initial_state(cleaned: str, session_id: str, context_messages: list,
                   widget_context: str = "", widget_context_verified: bool = False,
                   widget_facts: str = "") -> dict:
    return {
        "messages": context_messages,
        "user_input": cleaned,
        "session_id": session_id,
        "intent": {},
        "context": {},
        "analysis_result": {},
        "strategy": {},
        "token_usage": {},
        "tool_steps": 0,
        "guard_reason": "",
        "next_worker": "",
        "worker_history": [],
        "supervisor_plan": [],
        "llm_tier": "large",
        "security": {},
        "rag_hits": [],
        "widget_context": widget_context,
        "widget_context_verified": widget_context_verified,
        "widget_facts": widget_facts,
    }


async def _persist_turn(
    session_id: str,
    thread_id: str,
    user_text: str,
    ai_text: str,
    token_total: int = 0,
) -> None:
    """落盘一轮对话：会话文件（权威）+ 对话日志表（可审计/可回收）。

    两处都各自吞异常并告警：落盘失败属于旁路故障，不许影响主链路，
    也不许掩盖原始异常（否则真正的报错会被日志写失败顶掉）。
    """
    try:
        await session_memory.aappend_turn(session_id, user_text, ai_text)
    except Exception as e:
        logger.warning(f"[Chat] 会话落盘失败 session={session_id}: {e}")

    try:
        if user_text:
            await append_chat_log(
                session_id=session_id,
                thread_id=thread_id,
                role="human",
                content=user_text,
            )
        if ai_text and str(ai_text).strip():
            await append_chat_log(
                session_id=session_id,
                thread_id=thread_id,
                role="ai",
                content=ai_text,
                token_total=token_total,
            )
    except Exception as e:
        logger.warning(f"[Chat] 对话日志落库失败 session={session_id}: {e}")


async def _final_token_usage(graph, cfg: dict) -> int:
    """从 checkpoint 读回最终 state 的 token 用量（流式路径的成本口径）。"""
    try:
        snapshot = await graph.aget_state(cfg)
        values = getattr(snapshot, "values", None) or {}
        usage = values.get("token_usage") or {}
        return int(usage.get("total_tokens") or 0)
    except Exception as e:
        logger.warning(f"[ChatStream] 读取 token 用量失败: {e}")
        return 0


async def chat(
    message: str,
    session_id: str = None,
    thread_id: str = None,
    client_ip: str = "",
    widget_context: dict | None = None,
) -> dict:
    """非流式对话。"""
    if session_id is None:
        session_id = str(uuid.uuid4())
    thread_id = thread_id or session_id

    allowed, reason = await check_rate_limit(
        session_id=session_id, client_ip=client_ip
    )
    if not allowed:
        return {
            "reply": reason or "请求过于频繁，请稍后再试。",
            "session_id": session_id,
            "thread_id": thread_id,
            "rate_limited": True,
        }

    from agent.perception import preprocess
    cleaned = preprocess(message)
    logger.info(
        f"[Chat] session={session_id} thread_id={thread_id} message='{cleaned}'"
    )

    # “以后每天给我看退款趋势”这类偏好命令走确定性路径，不靠模型记得调工具
    pref_intent = detect_preference_intent(cleaned)
    if pref_intent:
        reply, saved = await apply_preference_intent(pref_intent)
        await _persist_turn(session_id, thread_id, cleaned, reply)
        logger.info(f"[Chat] preference intent action={pref_intent.action} saved={bool(saved)}")
        return {
            "reply": reply,
            "session_id": session_id,
            "thread_id": thread_id,
            "preference_saved": saved,
            "context_verified": None,
        }

    ctx = await validate_widget_context(widget_context)
    # 感知只算一次：意图同时用于 Langfuse 标签、RAG 向量腿策略与日志
    turn = inspect_turn(cleaned)
    intent_type = (turn.get("intent") or {}).get("intent") or "unknown"

    graph = get_agent_graph()
    cfg = _run_config(thread_id, session_id, turn)

    resumed = await resume_if_pending(graph, thread_id, session_id=session_id)
    if resumed is not None:
        logger.info(f"[Chat] 已续跑未完成线程 thread_id={thread_id}")

    ctx_kwargs = {"widget_context": ctx["text"]} if ctx.get("text") else {}
    context_messages, rag_hits = await _context_builder.abuild_context(
        session_id, cleaned, intent_type, **ctx_kwargs
    )
    initial = _initial_state(
        cleaned, session_id, context_messages,
        widget_context=ctx.get("text", ""),
        widget_context_verified=bool(ctx.get("verified")),
        widget_facts=ctx.get("facts", ""),
    )
    initial["rag_hits"] = rag_hits

    ai_reply = ""
    total_tokens = 0
    token_usage: dict = {}
    persist_user = cleaned
    try:
        result = await graph.ainvoke(initial, cfg)
        final_messages = result.get("messages", [])
        persist_user = result.get("user_input") or cleaned
        token_usage = result.get("token_usage", {}) or {}
        if final_messages:
            last = final_messages[-1]
            ai_reply = getattr(last, "content", "") or ""
        total_tokens = int((token_usage or {}).get("total_tokens") or 0)
        if token_usage:
            logger.info(f"[Chat] Token: {total_tokens}")
    finally:
        # 抛异常时也留痕：这一轮用户问了什么必须可追溯（ai_reply 可能为空）
        await _persist_turn(
            session_id, thread_id, persist_user, ai_reply, total_tokens
        )

    reply = {
        "reply": ai_reply,
        "session_id": session_id,
        "thread_id": thread_id,
        "rag_hits": compact_hits(rag_hits),
        "context_verified": ctx.get("verified") if widget_context else None,
    }
    if token_usage:
        reply["token_usage"] = token_usage
    return reply


async def resume_thread(thread_id: str, session_id: str = "") -> dict:
    """B6b：显式续跑上次未到 END 的线程；无断点或已完成则返回提示。"""
    sid = session_id or thread_id
    graph = get_agent_graph()
    result = await resume_if_pending(graph, thread_id, session_id=sid)
    if result is None:
        return {"resumed": False, "message": "没有待恢复的断点", "session_id": sid, "thread_id": thread_id}

    reply = ""
    for m in reversed(result.get("messages") or []):
        if (
            isinstance(m, AIMessage)
            and m.content
            and not getattr(m, "tool_calls", None)
            and not is_placeholder_content(str(m.content))
        ):
            reply = str(m.content)
            break

    if reply:
        await _persist_turn(sid, thread_id, "", reply)

    logger.info(f"[Resume] thread_id={thread_id} 续跑完成 reply_len={len(reply)}")
    return {"resumed": True, "reply": reply, "session_id": sid, "thread_id": thread_id}


async def chat_stream(
    message: str,
    session_id: str = None,
    thread_id: str = None,
    client_ip: str = "",
    widget_context: dict | None = None,
):
    """流式对话。R3：限流在返回生成器前检查，首字节前完成校验。"""
    if session_id is None:
        session_id = str(uuid.uuid4())
    thread_id = thread_id or session_id

    from agent.perception import preprocess
    cleaned = preprocess(message)
    logger.info(
        f"[ChatStream] session={session_id} thread_id={thread_id} message='{cleaned}'"
    )

    allowed, rate_reason = await check_rate_limit(
        session_id=session_id, client_ip=client_ip
    )

    # 与 chat() 一致：感知只算一次（限流之后、进图之前）
    pref_intent = detect_preference_intent(cleaned)
    turn = inspect_turn(cleaned)
    intent_type = (turn.get("intent") or {}).get("intent") or "unknown"

    async def async_generator():
        if not allowed:
            yield {"type": "content", "content": rate_reason or "请求过于频繁，请稍后再试。"}
            yield {"type": "rate_limited", "session_id": session_id}
            return

        if pref_intent:
            reply, saved = await apply_preference_intent(pref_intent)
            yield {"type": "content", "content": reply}
            if saved:
                yield {"type": "preference_saved", "preference": saved}
            if pref_intent.action != "help":
                yield {"type": "dashboard_updated"}
            await _persist_turn(session_id, thread_id, cleaned, reply)
            return

        graph = get_agent_graph()
        cfg = _run_config(thread_id, session_id, turn)
        accumulated = ""
        total_tokens = 0

        try:
            # 第一个事件也在 try 内：客户端在最开始就断开时，这一问同样要留痕
            yield {"type": "checkpoint", "thread_id": thread_id}

            resumed = await resume_if_pending(graph, thread_id, session_id=session_id)
            if resumed is not None:
                yield {
                    "type": "checkpoint_resumed",
                    "thread_id": thread_id,
                    "hint": "已从断点续跑完成上一未完成任务",
                }

            ctx = await validate_widget_context(widget_context)
            if widget_context:
                yield {
                    "type": "context",
                    "verified": bool(ctx.get("verified")),
                    "widget_id": ctx.get("widget_id"),
                    "selection": ctx.get("selection") or {},
                    "facts": ctx.get("facts") or "",
                }
            facts_text = ""
            if ctx.get("facts"):
                # 流式路径下模型输出是逐 token 直出的，call_llm 的后处理不会进入流；
                # 所以事实必须在这里先发，保证金额/百分比不会被模型改写。
                facts_text = f"数据事实（服务端快照）：{ctx['facts']}\n\n"
                accumulated += facts_text
                yield {"type": "content", "content": facts_text}
            stream_ctx_kwargs = {"widget_context": ctx["text"]} if ctx.get("text") else {}
            context_messages, rag_hits = await _context_builder.abuild_context(
                session_id, cleaned, intent_type, **stream_ctx_kwargs
            )
            initial_state = _initial_state(
                cleaned, session_id, context_messages,
                widget_context=ctx.get("text", ""),
                widget_context_verified=bool(ctx.get("verified")),
                widget_facts=ctx.get("facts", ""),
            )
            initial_state["rag_hits"] = rag_hits
            if rag_hits:
                yield {"type": "rag", "hits": compact_hits(rag_hits)}

            async for chunk in graph.astream(
                initial_state, cfg, stream_mode="messages"
            ):
                msg, metadata = chunk
                node = (metadata or {}).get("langgraph_node")

                if isinstance(msg, AIMessage):
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        if node in ("analyst", "call_llm", None):
                            for tc in msg.tool_calls:
                                yield {
                                    "type": "tool_call",
                                    "tool": tc["name"],
                                    "args": tc.get("args") or {},
                                }
                        continue

                    if msg.content:
                        if node != "call_llm":
                            continue
                        if is_placeholder_content(msg.content):
                            continue
                        accumulated += msg.content
                        yield {"type": "content", "content": msg.content}

                elif isinstance(msg, ToolMessage):
                    yield {
                        "type": "tool_result",
                        "tool": msg.name,
                        "result": msg.content[:200],
                    }

            # 流式路径同样要有成本口径：写进 agent_chat_log.token_total 并推给前端
            total_tokens = await _final_token_usage(graph, cfg)
            if total_tokens:
                yield {"type": "usage", "total_tokens": total_tokens}
                logger.info(f"[ChatStream] Token: {total_tokens}")
        finally:
            # 客户端点停止/断网、节点抛错、图未跑完都会走到这里：
            # 用户这一问必须落盘（回复可能是残缺或空的，也照样记录）
            await _persist_turn(
                session_id, thread_id, cleaned, accumulated.strip(), total_tokens
            )

    return async_generator()
