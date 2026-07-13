from langgraph.graph import StateGraph, START, END
builder = StateGraph(dict)
# 2. 加法节点
def addition(state):
    # 接收初始传入的全局状态
    print(f"init_state: {state}")
    # 仅更新x字段，LangGraph自动合并状态
    return {"x": state["x"] + 1}
# 3. 减法节点
def subtraction(state):
    # 接收上一个节点更新后的完整状态
    print(f"addition_state: {state}")
    return {"x": state["x"] - 2}
builder.add_node("addition", addition)
builder.add_node("subtraction", subtraction)

builder.add_edge(START, "addition")
builder.add_edge("addition", "subtraction")
builder.add_edge("subtraction", END)

graph = builder.compile()
print(graph)

graph_png = graph.get_graph(xray=True).draw_mermaid_png()
with open("flow_graph.png", "wb") as f:
    f.write(graph_png)
print("流程图已保存为 flow_graph.png")

# 定义初始化状态
initial_state = {"x": 10}
# 传入初始状态运行图
result = graph.invoke(initial_state)

print(result)