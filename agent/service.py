"""
Agent 对外服务（Service）

做什么：
- chat() / chat_stream()：组装上下文并跑 LangGraph
- 每轮带 thread_id（默认=session_id）写入 Checkpointer
- 若同 thread 有未完成 checkpoint，先 resume 再跑新一轮

不做什么：
- 不定义图（graph.py）
- 不定义节点（nodes.py）
"""

import uuid
import logging

from langchain_core.messages import AIMessage, ToolMessage

from agent.graph import get_agent_graph
from agent.checkpointing import thread_config, resume_if_pending
from agent.memory.session_memory import session_memory
from agent.memory.context_builder import ContextBuilder
from agent.knowledge.knowledge_base import knowledge_base
from agent.messages import is_placeholder_content

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
    }


async def chat(message: str, session_id: str = None, thread_id: str = None) -> dict:
    """非流式对话（异步，支持多轮 + checkpoint 续跑）。"""
    if session_id is None:
        session_id = str(uuid.uuid4())
    thread_id = thread_id or session_id

    from agent.perception import preprocess
    cleaned = preprocess(message)
    logger.info(
        f"[Chat] session={session_id} thread_id={thread_id} message='{cleaned}'"
    )

    graph = get_agent_graph()
    cfg = thread_config(thread_id)

    # 先消化未完成的断点（崩溃恢复场景）
    resumed = await resume_if_pending(graph, thread_id)
    if resumed is not None:
        logger.info(f"[Chat] 已续跑未完成线程 thread_id={thread_id}")

    context_messages = _context_builder.build_context(session_id, cleaned)
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

    session_memory.append_turn(session_id, user_input, ai_reply)

    reply = {
        "reply": ai_reply,
        "session_id": session_id,
        "thread_id": thread_id,
    }
    if token_usage:
        reply["token_usage"] = token_usage
        logger.info(f"[Chat] Token: {token_usage.get('total_tokens', 0)}")
    return reply


def chat_stream(message: str, session_id: str = None, thread_id: str = None):
    """
    流式对话。

    yield：
    - {"type": "content", ...}
    - {"type": "tool_call", ...}
    - {"type": "tool_result", ...}
    - {"type": "checkpoint", "thread_id": "..."}  （便于前端/调试对齐）
    """
    if session_id is None:
        session_id = str(uuid.uuid4())
    thread_id = thread_id or session_id

    from agent.perception import preprocess
    cleaned = preprocess(message)
    logger.info(
        f"[ChatStream] session={session_id} thread_id={thread_id} message='{cleaned}'"
    )

    context_messages = _context_builder.build_context(session_id, cleaned)
    initial_state = _initial_state(cleaned, session_id, context_messages)
    cfg = thread_config(thread_id)

    async def async_generator():
        accumulated = ""
        graph = get_agent_graph()

        yield {"type": "checkpoint", "thread_id": thread_id}

        resumed = await resume_if_pending(graph, thread_id)
        if resumed is not None:
            yield {
                "type": "checkpoint_resumed",
                "thread_id": thread_id,
                "hint": "已从断点续跑完成上一未完成任务",
            }

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

        session_memory.append_turn(session_id, cleaned, accumulated.strip())

    return async_generator()
