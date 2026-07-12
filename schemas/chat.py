"""
============================================================
请求/响应数据模型（schemas）
============================================================

【教学说明】这个文件是干什么的？
定义"数据长什么样"。

你在 Spring Boot 里，是不是写过这种类？

    public class ChatRequestDTO {
        @NotBlank
        private String message;
        private String sessionId;
    }

    public class ChatResponseVO {
        private String reply;
        private boolean success;
    }

Python 里用 Pydantic 做同样的事。Pydantic 会自动帮你校验数据：
- 如果要求 message 是 str，用户传了个数字进来，Pydantic 自动报错
- 如果某个字段有默认值，用户没传，就用默认值

【教学说明】为什么需要定义数据模型？
1. 代码可读性：别人一看就知道这个接口需要什么参数
2. 自动校验：不用手写 if message is None 这种判断
3. 自动生成 API 文档：FastAPI 会根据这些模型自动生成交互式文档

类比 Java：
    Pydantic BaseModel  =  Java 的 DTO/VO + @Valid 注解
    一个 Pydantic 类     =  一个 DTO 类
"""

from pydantic import BaseModel
from typing import Optional


# ============================================================
# 请求模型：前端发过来的数据长什么样？
# ============================================================
# 类比 Java：
#   public class ChatRequest {
#       @NotBlank(message = "消息不能为空")
#       private String message;
#       private String sessionId;
#   }
#
# 前端调用时发送的 JSON：
#   {
#     "message": "今天营业额多少？",
#     "session_id": "abc123"      ← 可选，用于多轮对话
#   }
# ============================================================
class ChatRequest(BaseModel):
    """
    聊天请求的数据模型。

    当商家在前端输入一句话点发送时，前端会把数据包装成 JSON 发过来。
    这个类定义了"前端应该发什么格式的数据"。
    """

    # 商家输入的消息（必填）
    # str = 字符串类型，类比 Java 的 String
    message: str

    # 会话ID（可选）
    # Optional[str] = 可以是字符串，也可以是 None（没传）
    # = None 表示默认值是 None
    # 类比 Java：private String sessionId; （没加 @NotBlank，所以可以为空）
    #
    # 【教学说明】为什么需要 session_id？
    # 阶段 5 会用到。商家连续问两个问题：
    #   "今天营业额多少？" → Agent 回答 "3580 元"
    #   "那昨天呢？"      → Agent 需要知道"昨天"是在问营业额
    # session_id 就是用来关联同一个商家的多轮对话的
    session_id: Optional[str] = None


# ============================================================
# 响应模型：Agent 返回给前端的数据长什么样？
# ============================================================
# 类比 Java：
#   public class ChatResponse {
#       private String reply;
#       private String sessionId;
#       private boolean success;
#   }
#
# 返回给前端的 JSON：
#   {
#     "reply": "今日营业额为 3580.00 元。",
#     "session_id": "abc123",
#     "success": true
#   }
# ============================================================
class ChatResponse(BaseModel):
    """
    聊天响应的数据模型。

    Agent 处理完商家的消息后，把回复包装成这个格式返回给前端。
    """

    # Agent 的回复内容
    reply: str

    # 会话ID（回传给前端，前端下次请求时带上）
    session_id: str

    # 是否成功
    success: bool = True
