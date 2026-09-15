"""
Agent 对外服务（Service）

做什么：
- chat() / chat_stream()：限流 → 上下文 → LangGraph → 会话/日志落盘
- thread_id + Checkpointer 续跑

不做什么：
- 不定义图 / 节点
"""

import uuid
import logging

from langchain_core.messages import AIMessage, ToolMessage

from agent.graph import get_agent_graph
from agent.checkpointing import thread_config, resume_if_pending
from agent.memory.session_memory import session_memory
from agent.memory.context_builder import ContextBuilder
from agent.memory.rate_limit import check_rate_limit
from agent.knowledge.knowledge_base import knowledge_base
from agent.messages import is_placeholder_content
from db.chat_log import append_chat_log

logger = logging.getLogger(__name__)

_context_builder = ContextBuilder(knowledge_base=knowledge_base)


def _initial_state(cleaned: str, session_id: str, context_messages: list) -> dict:
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
    }


async def chat(
    message: str,
    session_id: str = None,
    thread_id: str = None,
    client_ip: str = "",
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

    graph = get_agent_graph()
    cfg = thread_config(thread_id)

    resumed = await resume_if_pending(graph, thread_id)
    if resumed is not None:
        logger.info(f"[Chat] 已续跑未完成线程 thread_id={thread_id}")

    context_messages = await _context_builder.abuild_context(session_id, cleaned)
    result = await graph.ainvoke(
        _initial_state(cleaned, session_id, context_messages),
        cfg,
    )

    final_messages = result.get("messages", [])
    user_input = result.get("user_input", cleaned)
    token_usage = result.get("token_usage", {})

    ai_reply = ""
    if final_messages:
        last = final_messages[-1]
        ai_reply = getattr(last, "content", "") or ""

    await session_memory.aappend_turn(session_id, user_input, ai_reply)
    total_tokens = int((token_usage or {}).get("total_tokens") or 0)
    await append_chat_log(
        session_id=session_id,
        thread_id=thread_id,
        role="human",
        content=user_input,
    )
    await append_chat_log(
        session_id=session_id,
        thread_id=thread_id,
        role="ai",
        content=ai_reply,
        token_total=total_tokens,
    )

    reply = {
        "reply": ai_reply,
        "session_id": session_id,
        "thread_id": thread_id,
    }
    if token_usage:
        reply["token_usage"] = token_usage
        logger.info(f"[Chat] Token: {total_tokens}")
    return reply


def chat_stream(
    message: str,
    session_id: str = None,
    thread_id: str = None,
    client_ip: str = "",
):
    """流式对话。"""
    if session_id is None:
        session_id = str(uuid.uuid4())
    thread_id = thread_id or session_id

    from agent.perception import preprocess
    cleaned = preprocess(message)
    logger.info(
        f"[ChatStream] session={session_id} thread_id={thread_id} message='{cleaned}'"
    )

    async def async_generator():
        allowed, reason = await check_rate_limit(
            session_id=session_id, client_ip=client_ip
        )
        if not allowed:
            yield {"type": "content", "content": reason or "请求过于频繁，请稍后再试。"}
            yield {"type": "rate_limited", "session_id": session_id}
            return

        graph = get_agent_graph()
        cfg = thread_config(thread_id)
        accumulated = ""

        yield {"type": "checkpoint", "thread_id": thread_id}

        resumed = await resume_if_pending(graph, thread_id)
        if resumed is not None:
            yield {
                "type": "checkpoint_resumed",
                "thread_id": thread_id,
                "hint": "已从断点续跑完成上一未完成任务",
            }

        context_messages = await _context_builder.abuild_context(session_id, cleaned)
        initial_state = _initial_state(cleaned, session_id, context_messages)

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

        await session_memory.aappend_turn(session_id, cleaned, accumulated.strip())
        await append_chat_log(
            session_id=session_id,
            thread_id=thread_id,
            role="human",
            content=cleaned,
        )
        await append_chat_log(
            session_id=session_id,
            thread_id=thread_id,
            role="ai",
            content=accumulated.strip(),
        )

    return async_generator()
