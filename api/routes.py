"""
HTTP 路由：健康检查与聊天接口

FastAPI vs Spring Boot（仅接口层）：
  @GetMapping / @PostMapping  ≈  @app.get / @app.post
  @RequestBody DTO            ≈  Pydantic ChatRequest
"""

import hmac
import json
import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from config import settings
from schemas.chat import ChatRequest, ChatResponse, ResumeRequest, ResumeResponse
from agent.observability import tracing_ready

router = APIRouter()
logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    """B6b：SSE 帧带 event: 类型；data 内保留 type 字段兼容旧前端。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def require_auth(authorization: str = Header(default="")) -> None:
    """B0-A2：/api/* 端点鉴权。AGENT_API_TOKEN 为空时放行（开发模式，启动已告警）。"""
    token = settings.AGENT_API_TOKEN
    if not token:
        return
    if not hmac.compare_digest(authorization.strip(), f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="未授权：缺少或错误的 Bearer Token")


def _client_ip(request: Request) -> str:
    # B0-A6：x-forwarded-for 可伪造，仅可信反代部署时才采信
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for") or ""
        if forwarded:
            return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or ""
    return ""


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
        "version": settings.APP_VERSION,
        "langfuse": tracing_ready(),
        "auth_enabled": bool(settings.AGENT_API_TOKEN),
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
async def chat(request: ChatRequest, http_request: Request, _auth: None = Depends(require_auth)):
    """非流式聊天。"""
    from agent.service import chat as agent_chat

    session_id = request.session_id or str(uuid.uuid4())
    try:
        result = await agent_chat(
            message=request.message,
            session_id=session_id,
            thread_id=request.thread_id or session_id,
            client_ip=_client_ip(http_request),
        )
        return ChatResponse(
            reply=result["reply"],
            session_id=result["session_id"],
            thread_id=result.get("thread_id") or session_id,
            success=not result.get("rate_limited"),
            rag_hits=result.get("rag_hits") or None,
        )
    except Exception as e:
        logger.exception("[API] chat 失败: %s", e)
        return ChatResponse(
            reply=_friendly_llm_error(e),
            session_id=session_id,
            thread_id=request.thread_id or session_id,
            success=False,
        )


@router.post("/api/agent/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request, _auth: None = Depends(require_auth)):
    """流式聊天（SSE）。"""
    from agent.service import chat_stream as agent_chat_stream

    session_id = request.session_id or str(uuid.uuid4())
    thread_id = request.thread_id or session_id
    client_ip = _client_ip(http_request)

    async def event_generator():
        yield _sse("session", {"type": "session", "session_id": session_id, "thread_id": thread_id})
        try:
            stream = await agent_chat_stream(
                request.message,
                session_id,
                thread_id=thread_id,
                client_ip=client_ip,
            )
            async for chunk in stream:
                if isinstance(chunk, dict):
                    yield _sse(chunk.get("type") or "content", chunk)
                else:
                    yield _sse("content", {"type": "content", "content": chunk})
            yield _sse("done", {"type": "done"})
        except Exception as e:
            logger.exception("[API] chat_stream 失败: %s", e)
            yield _sse("error", {"type": "error", "message": _friendly_llm_error(e)})
            yield _sse("done", {"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@router.post("/api/agent/chat/resume", response_model=ResumeResponse)
async def chat_resume(request: ResumeRequest, _auth: None = Depends(require_auth)):
    """显式恢复断点线程（配合 CHECKPOINT_INTERRUPT_AFTER 演示 / 上次中断的会话）。"""
    from agent.service import resume_thread

    try:
        result = await resume_thread(thread_id=request.thread_id, session_id=request.session_id or "")
        return ResumeResponse(**result)
    except Exception as e:
        logger.exception("[API] chat_resume 失败: %s", e)
        return ResumeResponse(
            resumed=False,
            message=_friendly_llm_error(e),
            session_id=request.session_id or request.thread_id,
            thread_id=request.thread_id,
        )


@router.get("/api/agent/sessions")
async def list_sessions(_auth: None = Depends(require_auth)):
    """获取所有会话列表（用于前端会话管理）。"""
    from agent.memory.session_memory import session_memory

    sessions = session_memory.list_sessions()
    return {"sessions": sessions, "total": len(sessions)}


@router.delete("/api/agent/sessions/{session_id}")
async def delete_session(session_id: str, _auth: None = Depends(require_auth)):
    """删除指定会话。"""
    from agent.memory.session_memory import session_memory

    session_memory.clear_history(session_id)
    return {"success": True, "message": f"会话 {session_id} 已删除"}
