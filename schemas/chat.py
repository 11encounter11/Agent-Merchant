"""
============================================================
请求/响应数据模型（schemas）
============================================================

【教学说明】这个文件是干什么的？
定义"数据长什么样"。

Pydantic 会自动帮你校验数据：
- 如果要求 message 是 str，用户传了个数字进来，Pydantic 自动报错
- 如果某个字段有默认值，用户没传，就用默认值

为什么需要定义数据模型？
1. 代码可读性：别人一看就知道这个接口需要什么参数
2. 自动校验：不用手写 if message is None 这种判断
3. 自动生成 API 文档：FastAPI 会根据这些模型自动生成交互式文档
"""

from pydantic import BaseModel
from typing import Literal, Optional


# ============================================================
# 请求模型：前端发过来的数据长什么样？
# ============================================================
# 前端调用时发送的 JSON：
#   {
#     "message": "今天营业额多少？",
#     "session_id": "abc123"      ← 可选，用于多轮对话
#   }
# ============================================================
class ChatRequest(BaseModel):
    """聊天请求。"""

    message: str
    # 会话 ID：前端多轮对话；默认也用作 LangGraph thread_id
    session_id: Optional[str] = None
    # 可选：显式指定 checkpoint 线程（默认=session_id）
    thread_id: Optional[str] = None


class ChatResponse(BaseModel):
    """聊天响应。"""

    reply: str
    session_id: str
    thread_id: Optional[str] = None
    success: bool = True
    # RAG 命中来源（前端可忽略）
    rag_hits: Optional[list] = None


class ResumeRequest(BaseModel):
    """B6b 断点恢复请求：显式续跑上次未到 END 的线程。"""

    thread_id: str
    session_id: Optional[str] = None


class ResumeResponse(BaseModel):
    """断点恢复响应。"""

    resumed: bool
    reply: str = ""
    message: str = ""
    session_id: str = ""
    thread_id: str = ""


class FeedbackRequest(BaseModel):
    """B6d：对某轮回复点赞/点踩。"""

    session_id: str
    thread_id: Optional[str] = None
    rating: Literal["up", "down"]
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    success: bool
    message: str = ""
