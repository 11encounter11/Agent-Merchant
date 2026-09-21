"""
导出 LangGraph 流程图为 PNG（不在服务启动时自动执行）。

用法（在项目根目录）：
    python scripts/export_graph.py
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.graph import get_agent_graph


def main():
    out = _ROOT / "docs" / "flow_graph.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    png = get_agent_graph().get_graph(xray=True).draw_mermaid_png()
    out.write_bytes(png)
    print(f"流程图已保存为 {out}")


if __name__ == "__main__":
    main()
