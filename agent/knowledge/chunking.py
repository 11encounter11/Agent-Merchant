"""
文本切片

规定类 JSON 通常很短，整段入库即可。
超过 RAG_CHUNK_SIZE 的长文才切；overlap 避免句子被拦腰截断。

切片大小：
- 当前语料是短 FAQ/身份/节假日，默认切不到
- 有长文时：中文经验值约 300–800 字，overlap 约 10–20%
- 召回不准时：先看命中来源是 keyword 还是 vector，再决定改 keywords / embedding / 切片，而不是换 Milvus
"""

from __future__ import annotations


def split_if_long(text: str, chunk_size: int, overlap: int) -> list[str]:
    """短于 chunk_size 返回单段；否则按字符窗口切。"""
    text = (text or "").strip()
    if not text:
        return []
    if chunk_size <= 0 or len(text) <= chunk_size:
        return [text]

    step = max(chunk_size - max(overlap, 0), 1)
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start += step
    return chunks
