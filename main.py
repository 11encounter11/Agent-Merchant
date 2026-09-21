"""
苍穹外卖 - 商家智能助手 Agent 服务入口

启动：
  uvicorn main:app --host 0.0.0.0 --port 8100 --reload
  或：python main.py
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from agent.logging_config import setup_logging
from api.routes import router
from db.database import close_pool
from db.redis_client import close_redis
from db.chat_log import ensure_chat_log_table
from agent.observability import flush_tracing

logger = logging.getLogger(__name__)


def _interrupt_after_list() -> list[str] | None:
    raw = (settings.CHECKPOINT_INTERRUPT_AFTER or "").strip()
    if not raw:
        return None
    return [x.strip() for x in raw.split(",") if x.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动：挂 Checkpointer 并重编译图；关闭：释放资源。"""
    setup_logging(log_level=logging.INFO)

    if not settings.DB_PASSWORD:
        logger.warning("[Main] DB_PASSWORD 未配置：查数类工具将不可用（.env 中设置）")
    if not settings.AGENT_API_TOKEN:
        logger.warning("[Main] AGENT_API_TOKEN 未配置：/api/* 处于无鉴权开发模式")

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
            graph_mod.agent_graph = graph_mod.build_agent_graph(
                checkpointer, interrupt_after=interrupt_after
            )
            logger.info(f"[Main] Checkpointer=sqlite path={db_path}")
            await ensure_chat_log_table()
            yield
            flush_tracing()
            await close_redis()
    else:
        from langgraph.checkpoint.memory import MemorySaver

        graph_mod.agent_graph = graph_mod.build_agent_graph(
            MemorySaver(), interrupt_after=interrupt_after
        )
        logger.info("[Main] Checkpointer=memory（重启丢失）")
        await ensure_chat_log_table()
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
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,
    )
