"""
HTTP 路由：健康检查与聊天接口

FastAPI vs Spring Boot（仅接口层）：
  @GetMapping / @PostMapping  ≈  @app.get / @app.post
  @RequestBody DTO            ≈  Pydantic ChatRequest
"""

import asyncio
import hmac
import json
import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from fastapi.responses import StreamingResponse

from config import settings
from schemas.chat import (
    SESSION_ID_PATTERN,
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
    ResumeRequest,
    ResumeResponse,
)
from agent.observability import tracing_ready

router = APIRouter()
logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    """B6b：SSE 帧带 event: 类型；data 内保留 type 字段兼容旧前端。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _runtime_status() -> dict:
    """B6c：开关"声称值 + 实际生效状态"，供 /health 与配置后台核对。"""
    from db.redis_client import redis_status
    from agent.knowledge.knowledge_base import knowledge_base

    return {
        "redis": await redis_status(),
        "rate_limit": {"enabled": settings.RATE_LIMIT_ENABLED, "per_minute": settings.RATE_LIMIT_PER_MINUTE},
        "chat_log_enabled": settings.CHAT_LOG_ENABLED,
        "checkpoint_backend": settings.CHECKPOINT_BACKEND,
        "security_injection_enabled": settings.SECURITY_INJECTION_ENABLED,
        # 走 knowledge_base.status()：模块边界内的字段变化不会悄悄改坏 /health 契约
        "rag": knowledge_base.status(),
    }


def require_auth(authorization: str = Header(default="")) -> None:
    """B0-A2 / B7-S14：/api/* 端点鉴权。

    配置了 token → 必须带对的 Bearer；
    没配置 → dev 放行（本机联调），prod 直接 503。
    「没配置」不等于「不需要鉴权」：静默放行是 B0 之前最大的洞，
    换成 fail-closed 后，漏配 token 的后果从「裸奔」变成「明确拒绝」。
    """
    token = settings.AGENT_API_TOKEN
    if not token:
        if _is_prod():
            raise HTTPException(
                status_code=503,
                detail="服务未配置鉴权（prod 环境 fail-closed）：请设置 AGENT_API_TOKEN 或改用 APP_ENV=dev",
            )
        return
    if not hmac.compare_digest(authorization.strip(), f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="未授权：缺少或错误的 Bearer Token")


def _is_prod() -> bool:
    """APP_ENV=prod/production 视为生产环境（单一真值，供鉴权与启动日志共用）。"""
    return str(settings.APP_ENV).strip().lower() in {"prod", "production"}


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
    """把 LLM/依赖异常转成可读中文提示。

    不回显异常原文：异常串里常带内部 URL、驱动/请求细节，而错误路径是
    绕过 reflect 输出清洗的（那层只清洗模型回复）。完整异常由调用方
    logger.exception 落到服务端日志，客户端只拿可读结论。
    """
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
    if "DBUnavailable" in type(exc).__name__ or "数据库暂时不可用" in text:
        return "暂时取不到经营数据（数据库不可用），请稍后重试。"
    return "服务处理失败，请稍后重试；若持续失败请查看服务端日志。"


_SECRET_FIELDS = frozenset({
    "LLM_API_KEY", "EMBEDDING_API_KEY", "WEATHER_API_KEY", "DB_PASSWORD",
    "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "AGENT_API_TOKEN", "REDIS_URL",
})


@router.get("/health")
async def health_check():
    """健康检查 + 关键开关生效状态（B6c 第 1 级）。"""
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "langfuse": tracing_ready(),
        "env": settings.APP_ENV,
        # 三种状态：token 已配 / dev 无鉴权 / prod 缺配置（此时 /api/* 一律 503）
        "auth_enabled": bool(settings.AGENT_API_TOKEN),
        "auth_mode": (
            "token" if settings.AGENT_API_TOKEN else ("prod-closed" if _is_prod() else "dev-open")
        ),
        "runtime": await _runtime_status(),
    }


@router.get("/api/admin/config")
async def admin_config(_auth: None = Depends(require_auth)):
    """B6c 第 2 级：只读脱敏配置 + 运行时状态。凭据类只暴露"是否已配置"，永不回显值。"""
    plain, secrets = {}, {}
    for name in type(settings).model_fields:
        value = getattr(settings, name)
        if name in _SECRET_FIELDS:
            secrets[name] = bool(str(value).strip())
        else:
            plain[name] = value
    return {"config": plain, "secrets_configured": secrets, "runtime": await _runtime_status()}


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

        # 生产者在独立任务里驱动图，消费者按心跳间隔下发 `: ping`。
        # 为什么不用 wait_for 直接包 __anext__：超时会取消那次迭代，
        # 把 CancelledError 打进图里，等于「心跳把请求打死了」。
        queue: asyncio.Queue = asyncio.Queue()
        _done = object()

        async def produce():
            try:
                stream = await agent_chat_stream(
                    request.message,
                    session_id,
                    thread_id=thread_id,
                    client_ip=client_ip,
                )
                async for chunk in stream:
                    await queue.put(chunk)
            except Exception as e:
                logger.exception("[API] chat_stream 失败: %s", e)
                await queue.put({"type": "error", "message": _friendly_llm_error(e)})
            finally:
                await queue.put(_done)

        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(
                        # 下限 1s：配置成 0/负数会让 wait_for 立刻超时 → 变成 ping 死循环
                        queue.get(),
                        timeout=max(1.0, float(settings.SSE_HEARTBEAT_SEC)),
                    )
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if item is _done:
                    break
                if isinstance(item, dict):
                    yield _sse(item.get("type") or "content", item)
                else:
                    yield _sse("content", {"type": "content", "content": item})
            yield _sse("done", {"type": "done"})
        finally:
            # 客户端点停止/断网时不取消生产者：让它跑完并把这一轮落盘
            # （会话记忆 + 对话日志）。代价是这次 LLM 调用会完成——换来
            # 「中断的轮次也有权威记录」，比省一次调用更值。
            if not producer.done():
                logger.info("[API] 客户端断开，等待本轮收尾落盘 thread_id=%s", thread_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # 反代不缓冲：否则 token 是「攒够一块才吐」，流式体验变假
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
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


@router.post("/api/agent/feedback", response_model=FeedbackResponse)
async def chat_feedback(request: FeedbackRequest, _auth: None = Depends(require_auth)):
    """B6d：对回复点赞/点踩（差评样本后续喂 eval 回归集）。"""
    from db.feedback import append_feedback

    ok = await append_feedback(
        session_id=request.session_id,
        rating=request.rating,
        thread_id=request.thread_id or "",
        comment=request.comment or "",
    )
    return FeedbackResponse(
        success=ok,
        message="" if ok else "反馈暂未保存（存储降级），感谢你的意见",
    )


@router.get("/api/agent/sessions")
async def list_sessions(_auth: None = Depends(require_auth)):
    """获取所有会话列表（用于前端会话管理）。"""
    from agent.memory.session_memory import session_memory

    sessions = session_memory.list_sessions()
    return {"sessions": sessions, "total": len(sessions)}


@router.delete("/api/agent/sessions/{session_id}")
async def delete_session(
    session_id: str = Path(..., pattern=SESSION_ID_PATTERN, max_length=64),
    _auth: None = Depends(require_auth),
):
    """删除指定会话（session_id 会拼成文件名，必须先过白名单）。"""
    from agent.memory.session_memory import session_memory

    session_memory.clear_history(session_id)
    return {"success": True, "message": f"会话 {session_id} 已删除"}
