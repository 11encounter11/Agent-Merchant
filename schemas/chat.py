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

from pydantic import BaseModel, Field
from typing import Literal, Optional

# ============================================================
# 全局输入约束（单一真值）
# ============================================================
# 会话/线程 ID 会被用作文件名（data/sessions/<id>.json）、Redis key 与
# LangGraph thread_id。只允许安全字符：不含 . / \ 等路径分隔符，
# 防止「用户可控字符串 → 文件路径」的越权读写。空串按「未指定」处理。
SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{0,64}$"
# 单条消息长度上限：防超长输入打爆 token 预算与日志表
MAX_MESSAGE_CHARS = 4000

_SessionId = Field(default=None, pattern=SESSION_ID_PATTERN, max_length=64)


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

    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_CHARS)
    # 会话 ID：前端多轮对话；默认也用作 LangGraph thread_id
    session_id: Optional[str] = _SessionId
    # 可选：显式指定 checkpoint 线程（默认=session_id）
    thread_id: Optional[str] = _SessionId


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

    thread_id: str = Field(..., pattern=SESSION_ID_PATTERN, max_length=64)
    session_id: Optional[str] = _SessionId


class ResumeResponse(BaseModel):
    """断点恢复响应。"""

    resumed: bool
    reply: str = ""
    message: str = ""
    session_id: str = ""
    thread_id: str = ""


class FeedbackRequest(BaseModel):
    """B6d：对某轮回复点赞/点踩。"""

    session_id: str = Field(..., pattern=SESSION_ID_PATTERN, max_length=64)
    thread_id: Optional[str] = _SessionId
    rating: Literal["up", "down"]
    comment: Optional[str] = Field(default=None, max_length=500)


class FeedbackResponse(BaseModel):
    success: bool
    message: str = ""
