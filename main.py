"""
苍穹外卖 - 商家智能助手 Agent 服务入口

启动：
  uvicorn main:app --host 0.0.0.0 --port 8100 --reload
  或：python main.py
"""

import asyncio
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
from agent.logging_config import setup_logging
from api.routes import router
from api.workbench_routes import router as workbench_router
from db.database import close_pool
from db.redis_client import close_redis
from db.chat_log import ensure_chat_log_table
from db.feedback import ensure_feedback_table
from agent.observability import flush_tracing

logger = logging.getLogger(__name__)


def _interrupt_after_list() -> list[str] | None:
    raw = (settings.CHECKPOINT_INTERRUPT_AFTER or "").strip()
    if not raw:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


async def _warmup_knowledge_base() -> None:
    """启动预热知识库：读盘 + 建索引挪到启动期，别让首个用户请求替我们等。

    to_thread 是必须的：chromadb 与 embedding 都是同步阻塞调用，直接在
    事件循环里跑会把启动窗口内所有请求一起拖住。
    """
    if not settings.RAG_VECTOR_PRELOAD:
        return
    try:
        from agent.knowledge.knowledge_base import knowledge_base

        await asyncio.to_thread(knowledge_base.warmup)
    except Exception as e:
        logger.warning(f"[Main] 知识库预热失败（不影响启动，降级为关键词模式）: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动：挂 Checkpointer 并重编译图；关闭：释放资源。"""
    setup_logging(log_level=logging.INFO)

    if not settings.DB_PASSWORD:
        logger.warning("[Main] DB_PASSWORD 未配置：查数类工具将不可用（.env 中设置）")
    if not settings.AGENT_API_TOKEN:
        if str(settings.APP_ENV).strip().lower() in {"prod", "production"}:
            logger.error(
                "[Main] AGENT_API_TOKEN 未配置且 APP_ENV=prod：/api/* 一律 503（fail-closed）"
            )
        else:
            logger.warning("[Main] AGENT_API_TOKEN 未配置：/api/* 处于无鉴权开发模式（本机演示用）")

    import agent.graph as graph_mod

    interrupt_after = _interrupt_after_list()
    backend = (settings.CHECKPOINT_BACKEND or "memory").lower()

    if backend == "sqlite":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        db_path = settings.CHECKPOINT_SQLITE_PATH
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
            await checkpointer.setup()
            graph_mod.set_agent_graph(graph_mod.build_agent_graph(
                checkpointer, interrupt_after=interrupt_after
            ))
            logger.info(f"[Main] Checkpointer=sqlite path={db_path}")
            await ensure_chat_log_table()
            await ensure_feedback_table()
            await _warmup_knowledge_base()
            yield
            flush_tracing()
            await close_redis()
    else:
        from langgraph.checkpoint.memory import MemorySaver

        graph_mod.set_agent_graph(graph_mod.build_agent_graph(
            MemorySaver(), interrupt_after=interrupt_after
        ))
        logger.info("[Main] Checkpointer=memory（重启丢失）")
        await ensure_chat_log_table()
        await ensure_feedback_table()
        await _warmup_knowledge_base()
        yield
        flush_tracing()
        await close_redis()

    await close_pool()
    logger.info("[Main] Agent 服务已关闭，资源已释放")


app = FastAPI(
    title=settings.APP_NAME,
    description="面向外卖商家的智能经营助手 API",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _error_code(status: int) -> str:
    return {
        400: "INVALID_ARGUMENT",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        503: "SERVICE_UNAVAILABLE",
    }.get(status, "HTTP_ERROR")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "") or "req_unknown"


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    incoming = (request.headers.get("X-Request-ID") or "").strip()
    request.state.request_id = (
        incoming if _REQUEST_ID_PATTERN.match(incoming) else f"req_{uuid.uuid4().hex[:16]}"
    )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    headers = dict(exc.headers or {})
    code = headers.pop("X-Error-Code", "") or _error_code(exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": code,
            "request_id": _request_id(request),
        },
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(exc.errors()),
            "error_code": "VALIDATION_ERROR",
            "request_id": _request_id(request),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("[API] 未处理异常 request_id=%s", _request_id(request))
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务处理失败，请稍后重试",
            "error_code": "INTERNAL_ERROR",
            "request_id": _request_id(request),
        },
    )


app.include_router(router)
app.include_router(workbench_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,
    )
