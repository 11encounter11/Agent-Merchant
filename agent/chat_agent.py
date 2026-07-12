"""
============================================================
Agent 核心逻辑（用 LangGraph 构建）
============================================================

【教学说明】这个文件是整个 Agent 的"大脑"。
你之前学过 LangGraph，现在来看看在真实项目里它是怎么用的。

============================================================
先回忆一下 LangGraph 的 3 个核心概念（用大白话讲）：
============================================================

1. State（状态）= "整个图的记忆背包"
   - 图里所有节点共享的一个数据容器
   - 类比 Java：就像一个贯穿整个请求的 Context 对象
   - 比如：State 里存了 messages 列表，每个节点都能读到、往里面加消息

2. Node（节点）= "图里的一个处理站"
   - 每个节点是一个函数，接收 State，处理一下，返回更新后的 State
   - 类比 Java：就像一个 Service 方法
   - 比如：call_llm 节点 → 把消息发给 DeepSeek → 拿到回复 → 塞回 State

3. Edge（边）= "节点之间的连线"
   - 定义了"处理完 A 节点后，下一步去哪"
   - 类比 Java：就像 Controller 里调用 Service 的顺序
   - 比如：call_llm 处理完 → 直接结束（阶段 2 没有循环）

============================================================
阶段 2 的图非常简单（只有一个节点）：
============================================================

    [开始] → [call_llm 节点] → [结束]

    商家消息进来 → 发给 DeepSeek → 拿到回复 → 返回给商家

    阶段 3 加了 Tool 之后会变成：
    [开始] → [call_llm] → 要不要调Tool? → 要 → [tool节点] → 回到 [call_llm]
                                     → 不要 → [结束]
"""

import uuid
from typing import Annotated, Sequence
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from config import settings
from agent.prompts import SYSTEM_PROMPT_V1


# ============================================================
# 第一步：定义 State（图的"记忆背包"）
# ============================================================
# 【教学说明】TypedDict 是什么？
# 就是"有固定字段的字典"。类比 Java 的一个 POJO 类：
#
#   public class AgentState {
#       private List<Message> messages;  // 消息列表
#   }
#
# Python 用 TypedDict 来定义：
#   class AgentState(TypedDict):
#       messages: list  ← 消息列表
#
# 【教学说明】Annotated[..., add_messages] 是什么？
# 这是 LangGraph 的特殊语法。它告诉 LangGraph：
# "当多个节点往 messages 里加消息时，不要覆盖，而是追加"。
#
# 类比 Java：
#   普通的赋值：state.messages = newMessage   → 覆盖
#   add_messages：state.messages.add(newMessage) → 追加
#
# 这样商家说的每条消息、AI 回复的每条消息，都会保存下来，不会丢失。
# ============================================================
class AgentState(TypedDict):
    """
    Agent 的状态定义。

    整个 LangGraph 图里，所有节点共享这个 State。
    目前只有一个字段：messages（消息列表）。
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]


# ============================================================
# 第二步：创建 LLM 客户端
# ============================================================
# 【教学说明】ChatOpenAI 是什么？
# 它是 LangChain 封装的"LLM 客户端"。
# 虽然名字叫 ChatOpenAI，但 DeepSeek 的 API 兼容 OpenAI 格式，
# 所以我们设置 base_url 指向 DeepSeek 就行。
#
# 类比 Java：
#   RestTemplate restTemplate = new RestTemplate();
#   restTemplate.getForObject("https://api.deepseek.com/...", Response.class);
#
# ChatOpenAI 就是帮你封装了 HTTP 请求细节的"客户端"。
# 你只需要告诉它：
# - API Key（你的 DeepSeek 密钥）
# - Base URL（DeepSeek 的地址）
# - Model（用哪个模型）
# - Temperature（AI 的"创造性"，0=最稳定，1=最随机）
# ============================================================
llm = ChatOpenAI(
    api_key=settings.DEEPSEEK_API_KEY,     # 从 .env 读取的 API Key
    base_url=settings.DEEPSEEK_BASE_URL,   # https://api.deepseek.com
    model=settings.DEEPSEEK_MODEL,         # deepseek-chat
    temperature=0.7,                       # 0.7 是比较平衡的值（不太死板也不太发散）
)


# ============================================================
# 第三步：定义节点函数（Node）
# ============================================================
# 【教学说明】什么是节点函数？
# 就是一个普通函数，只不过它的输入和输出有固定格式：
# - 输入：当前的 State（包含 messages 列表）
# - 输出：要更新 State 的哪些字段
#
# 类比 Java：
#   public AgentState callLlm(AgentState state) {
#       List<Message> messages = state.getMessages();
#       Message aiReply = openAiClient.chat(messages);
#       messages.add(aiReply);
#       state.setMessages(messages);
#       return state;
#   }
#
# 下面这个 call_llm 做的事情一模一样，只是用 Python 写的。
# ============================================================
def call_llm(state: AgentState) -> dict:
    """
    调用 LLM 的节点。

    做的事情：
    1. 从 State 里取出 messages（消息列表）
    2. 在最前面加上 System Prompt（告诉 AI "你是谁"）
    3. 把完整的消息列表发给 DeepSeek
    4. 拿到 AI 的回复
    5. 把回复塞回 messages 里

    参数：
        state: 当前状态，包含 messages 列表

    返回：
        dict: 要更新的字段（这里只更新 messages）
    """

    # 取出当前的消息列表
    messages = state["messages"]

    # 在最前面加上 System Prompt
    # 【教学说明】为什么要加在最前面？
    # DeepSeek 的 API 规定：system 消息必须放在 messages 数组的第一个位置。
    # 它告诉 AI "你的角色是什么"，AI 会按照这个设定来回复。
    #
    # 类比 Java：
    #   List<Message> fullMessages = new ArrayList<>();
    #   fullMessages.add(new Message("system", SYSTEM_PROMPT));  ← 系统指令
    #   fullMessages.addAll(messages);                            ← 历史消息 + 当前消息
    #
    # Python 里用列表拼接：[a] + [b, c] = [a, b, c]
    system_message = SystemMessage(content=SYSTEM_PROMPT_V1)
    full_messages = [system_message] + list(messages)

    # 调用 LLM
    # 【教学说明】llm.invoke() 做了什么？
    # 它在内部帮你做了这些事：
    # 1. 把 messages 列表转换成 DeepSeek 要求的 JSON 格式
    # 2. 发一个 POST 请求到 https://api.deepseek.com/chat/completions
    # 3. 解析 DeepSeek 返回的 JSON
    # 4. 把 AI 的回复包装成 AIMessage 对象返回
    #
    # 类比 Java：
    #   Response response = restTemplate.postForObject(
    #       "https://api.deepseek.com/chat/completions",
    #       requestBody,
    #       Response.class
    #   );
    #   String aiReply = response.getChoices().get(0).getMessage().getContent();
    #
    # 一行代码搞定，底层帮你处理了所有 HTTP 细节。
    response = llm.invoke(full_messages)

    # 返回更新：把 AI 的回复追加到 messages 里
    # 【教学说明】为什么返回 dict 而不是整个 State？
    # LangGraph 的设计是"增量更新"：你只返回要改的字段就行。
    # 这里只更新 messages，其他字段不变。
    #
    # add_messages 会自动把 response 追加到已有的 messages 列表里。
    return {"messages": [response]}


# ============================================================
# 第四步：构建 LangGraph 图
# ============================================================
# 【教学说明】图是怎么"搭建"的？
# 就像搭积木：
# 1. 先创建一个空的图框架（StateGraph）
# 2. 往里面"放"节点（add_node）
# 3. 用边把节点"连"起来（add_edge）
# 4. 编译（compile）→ 得到一个可以运行的对象
#
# 类比 Java 的 Spring 配置类：
#   @Configuration
#   public class AgentConfig {
#       @Bean
#       public AgentGraph agentGraph() {
#           // 创建节点
#           // 连接节点
#           // 返回编译好的图
#       }
#   }
# ============================================================

# 创建图框架
# 类比 Java：new StateGraph<AgentState>(AgentState.class)
graph_builder = StateGraph(AgentState)

# 添加节点
# 类比 Java：graph.addNode("call_llm", this::callLlm)
graph_builder.add_node("call_llm", call_llm)

# 添加边（连线）
# START → call_llm → END
# 意思是：从"开始"进入 call_llm 节点，处理完后到"结束"
#
# 类比 Java：
#   graph.addEdge(START, "call_llm");
#   graph.addEdge("call_llm", END);
graph_builder.add_edge(START, "call_llm")
graph_builder.add_edge("call_llm", END)

# 编译图 → 得到一个可运行的对象
# 类比 Java：AgentGraph compiledGraph = graph.compile();
# 编译后会检查图的结构是否正确（比如有没有孤立的节点）
agent_graph = graph_builder.compile()


# ============================================================
# 第五步：封装一个方便调用的函数
# ============================================================
# 【教学说明】为什么要封装？
# 因为 main.py 里的接口函数不需要知道 LangGraph 的细节。
# 它只需要一个简单的方法：传入用户消息 → 拿到 AI 回复。
#
# 类比 Java 的 Service 层：
#   Controller 调 Service.chat(message)
#   Service 内部处理所有逻辑
#   Controller 不需要知道 Service 里面用了什么框架
# ============================================================
def chat(message: str, session_id: str = None) -> dict:
    """
    与 Agent 对话。

    参数：
        message: 商家输入的消息
        session_id: 会话ID（阶段 2 暂时不用，阶段 5 会用到）

    返回：
        dict: {
            "reply": "AI的回复内容",
            "session_id": "会话ID"
        }
    """

    # 如果没有传 session_id，自动生成一个
    if session_id is None:
        session_id = str(uuid.uuid4())

    # 把商家的消息包装成 HumanMessage（代表"人类说的话"）
    # 类比 Java：Message userMessage = new HumanMessage(message);
    user_message = HumanMessage(content=message)

    # 构造初始 State
    # 类比 Java：
    #   AgentState initialState = new AgentState();
    #   initialState.setMessages(Arrays.asList(userMessage));
    initial_state = {"messages": [user_message]}

    # 运行图！
    # agent_graph.invoke(initial_state) 会：
    # 1. 把 initial_state 传给 call_llm 节点
    # 2. call_llm 调用 DeepSeek，拿到回复
    # 3. 回复被追加到 messages 里
    # 4. 返回最终的 State（包含所有消息）
    #
    # 类比 Java：AgentState finalState = compiledGraph.invoke(initialState);
    result = agent_graph.invoke(initial_state)

    # 从最终 State 里取出 AI 的回复
    # messages[-1] 表示列表的最后一个元素（Python 的语法，-1 = 最后一个）
    # 因为 AI 的回复是最后加进去的，所以它在最后
    ai_reply = result["messages"][-1].content

    return {
        "reply": ai_reply,
        "session_id": session_id
    }


# ============================================================
# 第六步：流式聊天函数（SSE 版本）
# ============================================================
# 【教学说明】流式和非流式的区别？
#
# 非流式（上面的 chat 函数）：
#   llm.invoke(messages) → 等 DeepSeek 把整个回复生成完 → 一次性返回
#   用户需要等 3-5 秒才能看到回复
#
# 流式（下面的 chat_stream 函数）：
#   llm.stream(messages) → DeepSeek 每生成一个字就推一个字过来 → 实时显示
#   用户 0.5 秒后就能看到第一个字
#
# 类比 Java：
#   非流式 = restTemplate.getForObject() → 等响应完整再处理
#   流式   = WebClient 的 Flux 响应式流 → 收到一块就处理一块
#
# 【教学说明】yield 是什么？
# Python 的 yield 跟 Java 的 Iterator 类似。
# 普通函数用 return 返回一个值就结束了。
# 用 yield 的函数可以“一个一个返回”，每次 yield 产出一个值，
# 函数不结束，等你下次要的时候继续产出。
# 这就是“流式”的本质。
# ============================================================
def chat_stream(message: str, session_id: str = None):
    """
    流式聊天。一个字一个字地 yield AI 的回复。

    参数：
        message: 商家输入的消息
        session_id: 会话ID

    Yields（逐个产出）：
        str: AI 回复的一小段文字（通常是一个字或几个字）
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    # 准备消息（跟 chat 函数一样）
    system_message = SystemMessage(content=SYSTEM_PROMPT_V1)
    user_message = HumanMessage(content=message)
    full_messages = [system_message, user_message]

    # 用 stream 而不是 invoke
    # llm.stream() 返回一个生成器（generator），每生成一个 token 就产出一个值
    #
    # 类比 Java 的 Flux：
    #   Flux<String> tokens = openAiClient.streamChat(messages);
    #   tokens.subscribe(token -> sendToClient(token));
    #
    # Python 里用 for 循环就能逐个拿到 token
    for chunk in llm.stream(full_messages):
        # chunk.content 是这一次产出的文字片段（可能是几个字）
        if chunk.content:
            yield chunk.content
