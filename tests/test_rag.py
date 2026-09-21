"""RAG 命中来源 + 长文切片（不依赖 embedding / DB）。"""

from agent.knowledge.chunking import split_if_long
from agent.knowledge.knowledge_base import KnowledgeBase, compact_hits


def test_short_text_not_chunked():
    parts = split_if_long("端午节放假三天", chunk_size=500, overlap=50)
    assert parts == ["端午节放假三天"]


def test_long_text_is_chunked_with_overlap():
    text = "甲" * 120
    parts = split_if_long(text, chunk_size=50, overlap=10)
    assert len(parts) >= 3
    assert all(len(p) <= 50 for p in parts)
    # 相邻块应有重叠（第二块开头落在第一块窗口内）
    assert parts[1][0] in parts[0]


def test_keyword_hit_exposes_source_and_layer():
    kb = KnowledgeBase(enable_vector=False)
    kb._all_documents = [
        {
            "text": "2026年端午节是6月19日至6月21日",
            "keywords": ["端午", "端午节"],
            "source": "holidays",
            "chunk_id": "holidays_0",
        }
    ]
    hits = kb.search_hits("端午节那几天生意怎么样", use_vector=False)
    assert len(hits) == 1
    assert hits[0]["source"] == "holidays"
    assert hits[0]["layer"] == "keyword"
    assert hits[0]["matched_keyword"] in ("端午", "端午节")
    assert hits[0]["score"] == 1.0


def test_format_context_cites_source():
    kb = KnowledgeBase(enable_vector=False)
    text = kb.format_context([
        {
            "text": "我是苍穹外卖的智能经营顾问",
            "source": "identity",
            "layer": "keyword",
            "matched_keyword": "你是谁",
        }
    ])
    assert "来源:identity" in text
    assert "层:keyword" in text
    assert "命中:你是谁" in text


def test_load_json_keeps_source_and_skips_chunk_when_short():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as raw:
        data_dir = Path(raw)
        (data_dir / "holidays.json").write_text(
            '[{"keywords": ["端午"], "text": "端午放假"}]',
            encoding="utf-8",
        )
        kb = KnowledgeBase(enable_vector=False)
        kb.load_data(str(data_dir))
        assert len(kb._all_documents) == 1
        assert kb._all_documents[0]["source"] == "holidays"
        assert kb._all_documents[0]["chunk_id"] == "holidays_0"


def test_load_long_txt_chunks():
    import tempfile
    from pathlib import Path
    from config import settings

    with tempfile.TemporaryDirectory() as raw:
        data_dir = Path(raw)
        (data_dir / "wiki.txt").write_text("乙" * 1200, encoding="utf-8")
        kb = KnowledgeBase(enable_vector=False)
        old_size, old_overlap = settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP
        settings.RAG_CHUNK_SIZE = 400
        settings.RAG_CHUNK_OVERLAP = 40
        try:
            kb.load_data(str(data_dir))
            assert len(kb._all_documents) > 1
            assert all(d["source"] == "wiki" for d in kb._all_documents)
            assert any("_c" in d["chunk_id"] for d in kb._all_documents)
        finally:
            settings.RAG_CHUNK_SIZE = old_size
            settings.RAG_CHUNK_OVERLAP = old_overlap


def test_compact_hits_drops_full_text():
    compact = compact_hits([{
        "text": "x" * 200,
        "source": "faq",
        "layer": "keyword",
        "score": 1.0,
        "matched_keyword": "退款",
        "chunk_id": "faq_1",
    }])
    assert compact[0]["source"] == "faq"
    assert compact[0]["layer"] == "keyword"
    assert len(compact[0]["preview"]) <= 80
    assert "text" not in compact[0]


def test_no_hit_returns_empty():
    kb = KnowledgeBase(enable_vector=False)
    kb._all_documents = []
    assert kb.search_hits("随便问问", use_vector=False) == []


def test_context_builder_injects_cited_hits():
    from langchain_core.messages import HumanMessage
    from agent.memory.context_builder import ContextBuilder

    class _FakeKB:
        def search_hits(self, query, use_vector=True):
            return [{
                "text": "2026年端午节是6月19日至6月21日",
                "source": "holidays",
                "layer": "keyword",
                "matched_keyword": "端午",
                "score": 1.0,
                "chunk_id": "holidays_0",
            }]

        def format_context(self, results):
            return KnowledgeBase(enable_vector=False).format_context(results)

    builder = ContextBuilder(knowledge_base=_FakeKB())
    messages, hits = builder._assemble("s1", "端午节怎么放假", [])
    assert hits[0]["source"] == "holidays"
    assert isinstance(messages[0], HumanMessage)
    assert "来源:holidays" in messages[0].content
    assert messages[-1].content == "端午节怎么放假"
