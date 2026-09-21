"""pytest 全局配置：保证从任意目录运行 `pytest` 都能 import 项目模块。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
