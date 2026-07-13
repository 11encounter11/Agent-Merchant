from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI

# 1. 定义状态
class State(TypedDict):
    messages: Annotated[list, add_messages]

# 初始化大模型
model = ChatOpenAI(model="gpt-3.5-turbo")

# 2. 定义节点
def chatbot(state: State):
    return {"messages": [model.invoke(state["messages"])]}

# 3. 构建图
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_edge(START, "chatbot")
graph = graph_builder.compile()

# 4. 执行对话
res = graph.invoke({"messages": [("user", "简单介绍LangGraph")]})
print(res["messages"][-1].content)