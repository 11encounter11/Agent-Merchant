"""
逐步打印 LangGraph 每一步的 state 变化。

用法（在项目根目录）：
    python scripts/trace_state.py "今天营业额多少？"
    python scripts/trace_state.py "你好"
    python scripts/trace_state.py "今天营业额多少？" --session demo-001
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

# 保证可以从项目根导入 agent / config
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _msg_to_dict(msg) -> dict:
    """把 LangChain Message 转成可读 dict。"""
    data = {
        "type": type(msg).__name__,
        "content": (getattr(msg, "content", None) or "")[:300],
    }
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        data["tool_calls"] = [
            {
                "name": tc.get("name"),
                "args": tc.get("args"),
                "id": tc.get("id"),
            }
            for tc in tool_calls
        ]
    if type(msg).__name__ == "ToolMessage":
        data["name"] = getattr(msg, "name", None)
        data["tool_call_id"] = getattr(msg, "tool_call_id", None)
    return data


def _state_to_dict(state: dict) -> dict:
    """把 AgentState 转成可 JSON 打印的结构。"""
    return {
        "user_input": state.get("user_input"),
        "session_id": state.get("session_id"),
        "token_usage": state.get("token_usage") or {},
        "messages": [_msg_to_dict(m) for m in state.get("messages", [])],
    }


def _print_block(title: str, payload) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="逐步追踪 Agent state")
    parser.add_argument("question", help="用户问题")
    parser.add_argument(
        "--session",
        default=None,
        help="会话 ID（默认随机生成）",
    )
    args = parser.parse_args()

    # 延迟导入：避免 --help 时也去连模型/知识库
    from agent.graph import get_agent_graph
    agent_graph = get_agent_graph()
    from agent.perception import perception

    session_id = args.session or str(uuid.uuid4())
    cleaned = perception.preprocess(args.question)

    initial_state = {
        "messages": [],
        "user_input": cleaned,
        "session_id": session_id,
        "token_usage": {},
    }

    _print_block(
        f"[初始 state] session={session_id}",
        _state_to_dict(initial_state),
    )

    step = 0
    # updates: 每个节点返回了什么
    # values: 合并后的完整 state
    for mode, chunk in agent_graph.stream(
        initial_state,
        stream_mode=["updates", "values"],
    ):
        if mode == "updates":
            # chunk 形如 {"call_llm": {"messages": [...], ...}}
            for node_name, update in chunk.items():
                step += 1
                printable_update = dict(update)
                if "messages" in printable_update:
                    printable_update["messages"] = [
                        _msg_to_dict(m) for m in printable_update["messages"]
                    ]
                _print_block(
                    f"[步骤 {step}] 节点 `{node_name}` 返回的更新 (updates)",
                    printable_update,
                )
        elif mode == "values":
            _print_block(
                f"[步骤 {step}] 合并后的完整 state (values)",
                _state_to_dict(chunk),
            )

    print("\n" + "=" * 72)
    print("追踪结束。看 should_continue 前后的 call_llm / tools 循环即可理解分流。")
    print("=" * 72)


if __name__ == "__main__":
    main()
