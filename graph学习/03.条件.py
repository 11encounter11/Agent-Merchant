from typing import Optional
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END

# 1. 基于Pydantic定义结构化状态
class MyState(BaseModel):
    x: int
    result: Optional[str] = None

# 2. 普通业务节点（接收并返回完整MyState对象）
def check_x(state: MyState) -> MyState:
    print(f"[check_x] Received state: {state}")
    return state

# 3. 条件分支判断函数（接收state，返回布尔值用于路由分支）
def is_even(state: MyState) -> bool:
    return state.x % 2 == 0
# 偶数处理节点
def handle_even(state: MyState) -> MyState:
    print("[handle_even] x 是偶数")
    return MyState(x=state.x, result="even")

# 奇数处理节点
def handle_odd(state: MyState) -> MyState:
    print("[handle_odd] x 是奇数")
    return MyState(x=state.x, result="odd")

# 构建图
builder = StateGraph(MyState)

# 添加节点
builder.add_node("check_x", check_x)
builder.add_node("handle_even", handle_even)
builder.add_node("handle_odd", handle_odd)



# 衔接起始、结束节点
builder.add_edge(START, "check_x")

# 添加条件分支路由
builder.add_conditional_edges(
    "check_x",
    is_even,
    {
        True: "handle_even",
        False: "handle_odd"
    }
)

builder.add_edge("handle_even", END)
builder.add_edge("handle_odd", END)

# 编译生成可运行图实例
graph = builder.compile()

# 测试偶数分支
print("\n✅ 测试 x=4（偶数）")
graph.invoke(MyState(x=4))

# 测试奇数分支
print("\n✅ 测试 x=3（奇数）")
graph.invoke(MyState(x=3))

graph_png = graph.get_graph(xray=True).draw_mermaid_png()
with open("flow_graph_条件.png", "wb") as f:
    f.write(graph_png)
print("流程图已保存为 flow_graph_条件.png")