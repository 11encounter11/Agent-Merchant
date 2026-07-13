from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END

# 1. 定义循环状态
class LoopState(BaseModel):
    x: int

# 2. 自增节点
def increment(state: LoopState) -> LoopState:
    print(f"[increment] 当前 x = {state.x}")
    return LoopState(x=state.x + 1)

# 3. 循环终止判断函数
def is_done(state: LoopState) -> bool:
    return state.x > 10

# 4. 构建图
builder = StateGraph(LoopState)
builder.add_node("increment", increment)

# 条件分支实现循环
builder.add_conditional_edges(
    "increment",
    is_done,
    {
        True: END,
        False: "increment"
    }
)

# 入口边
builder.add_edge(START, "increment")

# 编译运行
graph = builder.compile()
graph.invoke(LoopState(x=0))

graph_png = graph.get_graph(xray=True).draw_mermaid_png()
with open("flow_graph_循环.png", "wb") as f:
    f.write(graph_png)
print("流程图已保存为 flow_graph_循环.png")