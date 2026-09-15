"""
HTTP 路由：健康检查与聊天接口

FastAPI vs Spring Boot（仅接口层）：
  @GetMapping / @PostMapping  ≈  @app.get / @app.post
  @RequestBody DTO            ≈  Pydantic ChatRequest
"""

import json
import logging
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from config import settings
from schemas.chat import ChatRequest, ChatResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def _friendly_llm_error(exc: Exception) -> str:
    """把 LLM/依赖异常转成可读中文提示。"""
    text = str(exc)
    if "FreeTierOnly" in text or "free quota has been exhausted" in text.lower():
        return (
            "通义千问免费额度已用完。请到阿里云 DashScope 控制台充值，"
            "或关闭「仅使用免费额度」后再试。"
        )
    if "401" in text or "invalid_api_key" in text.lower():
        return "LLM API Key 无效，请检查 .env 中的 LLM_API_KEY。"
    if "429" in text or "rate" in text.lower():
        return "LLM 请求过于频繁，请稍后再试。"
    return f"服务处理失败：{text[:200]}"


@router.get("/health")
async def health_check():
    """健康检查。"""
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": "0.1.0",
    }


@router.get("/")
async def root():
    """根路径欢迎信息。"""
    return {
        "message": "欢迎使用苍穹外卖商家智能助手 Agent 服务！",
        "docs": "/docs",
        "health": "/health",
    }


@router.post("/api/agent/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """非流式聊天。"""
    from agent.service import chat as agent_chat

    session_id = request.session_id or str(uuid.uuid4())
    try:
        result = await agent_chat(
            message=request.message,
            session_id=session_id,
            thread_id=request.thread_id or session_id,
        )
        return ChatResponse(
            reply=result["reply"],
            session_id=result["session_id"],
            thread_id=result.get("thread_id") or session_id,
            success=True,
        )
    except Exception as e:
        logger.exception("[API] chat 失败: %s", e)
        return ChatResponse(
            reply=_friendly_llm_error(e),
            session_id=session_id,
            success=False,
        )


@router.post("/api/agent/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天（SSE）。"""
    from agent.service import chat_stream as agent_chat_stream

    session_id = request.session_id or str(uuid.uuid4())
    thread_id = request.thread_id or session_id

    async def event_generator():
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id, 'thread_id': thread_id}, ensure_ascii=False)}\n\n"
        try:
            async for chunk in agent_chat_stream(
                request.message, session_id, thread_id=thread_id
            ):
                if isinstance(chunk, dict):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.exception("[API] chat_stream 失败: %s", e)
            yield f"data: {json.dumps({'type': 'content', 'content': _friendly_llm_error(e)}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.get("/api/agent/sessions")
async def list_sessions():
    """获取所有会话列表（用于前端会话管理）。"""
    from agent.memory.session_memory import session_memory

    sessions = session_memory.list_sessions()
    return {"sessions": sessions, "total": len(sessions)}


@router.delete("/api/agent/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除指定会话。"""
    from agent.memory.session_memory import session_memory

    session_memory.clear_history(session_id)
    return {"success": True, "message": f"会话 {session_id} 已删除"}
