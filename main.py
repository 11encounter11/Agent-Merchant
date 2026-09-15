"""
苍穹外卖 - 商家智能助手 Agent 服务入口

启动：
  uvicorn main:app --host 0.0.0.0 --port 8100 --reload
  或：python main.py
"""

import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from agent.logging_config import setup_logging
from api.routes import router
from db.database import close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时设置日志，关闭时释放资源。"""
    setup_logging(log_level=logging.INFO)
    yield
    # 服务关闭：释放数据库连接池
    await close_pool()
    logging.getLogger(__name__).info("[Main] Agent 服务已关闭，资源已释放")


app = FastAPI(
    title=settings.APP_NAME,
    description="面向外卖商家的智能经营助手 API",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
