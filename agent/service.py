"""
Agent 对外服务（Service）

做什么：
- 提供 chat()（非流式）和 chat_stream()（流式）接口
- 会话落盘统一走 session_memory.append_turn
- 适配新的 AgentState（包含 intent、context、analysis_result、strategy 等字段）

不做什么：
- 不定义图（在 graph.py）
- 不定义节点（在 nodes.py）
"""

import uuid
import logging

from langchain_core.messages import AIMessage, ToolMessage

from agent.graph import agent_graph
from agent.memory.session_memory import session_memory
from agent.memory.context_builder import ContextBuilder
from agent.knowledge.knowledge_base import knowledge_base
from agent.messages import is_placeholder_content

logger = logging.getLogger(__name__)

# 注入现有 JSON/RAG 知识库，规定类问题可进对话
_context_builder = ContextBuilder(knowledge_base=knowledge_base)


async def chat(message: str, session_id: str = None) -> dict:
    """非流式对话（异步，支持多轮）。"""
    if session_id is None:
        session_id = str(uuid.uuid4())

    from agent.perception import preprocess
    cleaned = preprocess(message)
    logger.info(f"[Chat] 非流式对话: session={session_id}, message='{cleaned}'")

    # 组装上下文（历史 + RAG + 当前输入）
    context_messages = _context_builder.build_context(session_id, cleaned)

    result = await agent_graph.ainvoke({
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
    })

    final_messages = result.get("messages", [])
    user_input = result.get("user_input", cleaned)
    token_usage = result.get("token_usage", {})

    ai_reply = ""
    if final_messages:
        last = final_messages[-1]
        ai_reply = getattr(last, "content", "") or ""

    # 落盘
    session_memory.append_turn(session_id, user_input, ai_reply)

    reply = {
        "reply": ai_reply,
        "session_id": session_id,
    }

    if token_usage:
        reply["token_usage"] = token_usage
        total = token_usage.get("total_tokens", 0)
        logger.info(f"[Chat] 本轮消耗 Token: {total}")

    return reply


def chat_stream(message: str, session_id: str = None):
    """
    流式对话。

    yield 字典：
    - {"type": "content", "content": "..."}
    - {"type": "tool_call", "tool": "...", "args": {...}}
    - {"type": "tool_result", "tool": "...", "result": "..."}
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    from agent.perception import preprocess
    cleaned = preprocess(message)
    logger.info(f"[ChatStream] 流式对话: session={session_id}, message='{cleaned}'")

    context_messages = _context_builder.build_context(session_id, cleaned)

    initial_state = {
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
    }

    async def async_generator():
        accumulated = ""

        async for chunk in agent_graph.astream(initial_state, stream_mode="messages"):
            msg, metadata = chunk
            node = (metadata or {}).get("langgraph_node")

            if isinstance(msg, AIMessage):
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    # analyst 发出的工具调用也要推给前端
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
