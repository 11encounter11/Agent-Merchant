from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel

# 1. 用Pydantic BaseModel定义结构化状态
class CalcState(BaseModel):
    x: int

# 2. 节点函数，入参、返回值均为CalcState对象
def addition(state: CalcState) -> CalcState:
    print(f"[addition] 初始状态: {state}")
    return CalcState(x=state.x + 1)

def subtraction(state: CalcState) -> CalcState:
    print(f"[subtraction] 接收到状态: {state}")
    return CalcState(x=state.x - 2)

# 3. 构建状态图
builder = StateGraph(CalcState)
builder.add_node("addition", addition)
builder.add_node("subtraction", subtraction)

# 定义流转边
builder.add_edge(START, "addition")
builder.add_edge("addition", "subtraction")
builder.add_edge("subtraction", END)

# 编译运行
graph = builder.compile()
init_state = CalcState(x=10)
res = graph.invoke(init_state)
print("最终结果:", res)

