from typing import TypedDict
from langgraph.graph import StateGraph, START, END

# 1. 定义全局状态State
class HelloState(TypedDict):
    name: str
    greeting: str

# 2. 定义流程节点函数
def greet(state: HelloState) -> dict:
    name = state["name"]
    return {"greeting": f"你好，{name}！"}

def add_emoji(state: HelloState) -> dict:
    greeting = state["greeting"]
    return {"greeting": greeting + "😊"}

# 3. 构建状态图实例
graph = StateGraph(HelloState)

# 添加节点
graph.add_node("greet", greet)
graph.add_node("add_emoji", add_emoji)

# 设置流程边（流转顺序）
graph.add_edge(START, "greet")
graph.add_edge("greet", "add_emoji")
graph.add_edge("add_emoji", END)

# 4. 编译图生成可运行实例
app = graph.compile()

# 5. 调用执行图
result = app.invoke({"name": "张三"})
print(result["greeting"])  # 输出：你好，张三！😊``

# 可视化绘图代码（仅jupyter环境可用）
# from IPython.display import Image, display
# display(Image(app.get_graph().draw_mermaid_png()))