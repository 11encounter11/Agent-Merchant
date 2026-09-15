"""
长期偏好记忆（Long Term Memory）

做什么：
- 记录商家的经营偏好（关注的指标、常用的分析维度）
- 记录历史决策（商家采纳过哪些建议）
- JSON 文件持久化

不做什么：
- 不做会话历史（那是 session_memory 的事）
- 不做 RAG 检索（那是 knowledge_base 的事）

当前状态：预留骨架，后续迭代完善。
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PREFS_DIR = Path(__file__).parent.parent.parent / "data" / "preferences"


class LongTermMemory:
    """长期偏好记忆（预留骨架）。"""

    def __init__(self):
        self._prefs: dict = {}

    def get_preference(self, session_id: str, key: str) -> Optional[str]:
        """获取商家偏好。"""
        prefs = self._load_prefs(session_id)
        return prefs.get(key)

    def set_preference(self, session_id: str, key: str, value: str):
        """记录商家偏好。"""
        prefs = self._load_prefs(session_id)
        prefs[key] = value
        self._save_prefs(session_id, prefs)

    def _load_prefs(self, session_id: str) -> dict:
        PREFS_DIR.mkdir(parents=True, exist_ok=True)
        filepath = PREFS_DIR / f"{session_id}.json"
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_prefs(self, session_id: str, prefs: dict):
        PREFS_DIR.mkdir(parents=True, exist_ok=True)
        filepath = PREFS_DIR / f"{session_id}.json"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(prefs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[LongTermMemory] 保存失败: {e}")


# 全局实例
long_term_memory = LongTermMemory()
