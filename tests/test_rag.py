"""RAG 命中来源 + 长文切片（不依赖 embedding / DB）。"""

from agent.knowledge.chunking import split_if_long
from agent.knowledge.knowledge_base import KnowledgeBase, compact_hits
from config import settings


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


def test_load_long_txt_chunks(monkeypatch):
    import tempfile
    from pathlib import Path
    from config import settings

    monkeypatch.setattr(settings, "RAG_CHUNK_SIZE", 400)
    monkeypatch.setattr(settings, "RAG_CHUNK_OVERLAP", 40)
    with tempfile.TemporaryDirectory() as raw:
        data_dir = Path(raw)
        (data_dir / "wiki.txt").write_text("乙" * 1200, encoding="utf-8")
        kb = KnowledgeBase(enable_vector=False)
        kb.load_data(str(data_dir))
        assert len(kb._all_documents) > 1
        assert all(d["source"] == "wiki" for d in kb._all_documents)
        assert any("_c" in d["chunk_id"] for d in kb._all_documents)


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
        def search_hits(self, query, use_vector=True, intent_type=""):
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


# ---------------------------------------------------------------
# 向量腿策略（不联网：用假 collection 顶替 chromadb）
# ---------------------------------------------------------------


class _FakeCollection:
    """最小 chroma 接口：count / query / upsert。记录调用次数以便断言「有没有打 embedding」。"""

    def __init__(self, docs=(), dists=(), metas=(), ids=()):
        self._docs = list(docs)
        self._dists = list(dists)
        self._metas = list(metas)
        self._ids = list(ids)
        self.query_calls = 0

    def count(self):
        return len(self._docs)

    def upsert(self, documents=None, ids=None, metadatas=None):
        return None

    def query(self, query_texts=None, n_results=None, include=None):
        self.query_calls += 1
        return {
            "documents": [self._docs],
            "distances": [self._dists],
            "metadatas": [self._metas],
            "ids": [self._ids],
        }


def _kb_with_vector(dists, docs=("语义召回的文本",), metas=None):
    kb = KnowledgeBase(enable_vector=False)
    kb._all_documents = []
    # 模拟「已预热」：跳过 load_data（否则会去读真实 data/ 并覆盖 collection）
    kb._loaded = True
    kb._ready = True
    kb._initialized = True
    kb.collection = _FakeCollection(
        docs=docs,
        dists=dists,
        metas=metas or [{"source": "holidays", "chunk_id": "holidays_0", "document_id": "holidays"}],
        ids=["holidays_0"],
    )
    return kb


def test_analytic_intent_never_calls_vector_leg():
    """数据类问题不补向量：否则知识片段会被塞进经营分析的上下文。"""
    kb = _kb_with_vector([0.1])
    hits = kb.search_hits("今天营业额多少", intent_type="query_analysis")
    assert kb.collection.query_calls == 0
    assert hits == []


def test_keyword_miss_on_knowledge_question_backfills_vector():
    kb = _kb_with_vector([0.2])
    hits = kb.search_hits("小长假那几天生意会好吗", intent_type="unknown")
    assert kb.collection.query_calls == 1
    assert [h["layer"] for h in hits] == ["vector"]


def test_low_score_vector_hit_is_dropped(monkeypatch):
    """距离 10 → 相似度 0.09 < 阈值：向量层总能返回「最近的」，不该照单注入。"""
    monkeypatch.setattr(settings, "RAG_VECTOR_MIN_SCORE", 0.45)
    kb = _kb_with_vector([10.0])
    hits = kb.search_hits("小长假那几天生意会好吗", intent_type="unknown")
    assert kb.collection.query_calls == 1
    assert hits == []


def test_vector_backfill_disabled_by_config(monkeypatch):
    monkeypatch.setattr(settings, "RAG_VECTOR_BACKFILL", False)
    kb = _kb_with_vector([0.1])
    kb.search_hits("小长假那几天生意会好吗", intent_type="unknown")
    assert kb.collection.query_calls == 0


def test_vector_hit_keeps_metadata(monkeypatch):
    monkeypatch.setattr(settings, "RAG_VECTOR_MIN_SCORE", 0.45)
    kb = _kb_with_vector(
        [0.2],
        metas=[{
            "source": "holidays",
            "document_id": "holidays",
            "chunk_id": "holidays_6",
            "title": "端午节",
            "version": "06-19",
        }],
    )
    hits = kb.search_hits("小长假那几天生意会好吗", intent_type="unknown")
    assert hits[0]["title"] == "端午节"
    assert hits[0]["version"] == "06-19"
    assert hits[0]["document_id"] == "holidays"
    ctx = kb.format_context(hits)
    assert "条目:端午节" in ctx and "版本:06-19" in ctx


def test_chunk_metadata_carries_locator_and_version():
    kb = KnowledgeBase(enable_vector=False)
    docs, ids, metas = [], [], []
    kb._ingest_text(
        source="holidays",
        text="2026年端午节是6月19日至6月21日",
        keywords=["端午"],
        item_index=6,
        documents=docs,
        ids=ids,
        metadatas=metas,
        title="端午节",
        version="06-19",
    )
    assert metas[0]["document_id"] == "holidays"
    assert metas[0]["title"] == "端午节"
    assert metas[0]["version"] == "06-19"
    assert kb._all_documents[0]["chunk_id"] == "holidays_6"


def test_status_exposes_public_state():
    kb = KnowledgeBase(enable_vector=False)
    st = kb.status()
    assert set(st) >= {"vector_enabled", "vector_ready", "loaded", "documents", "chunks_in_index"}


def test_vector_index_is_persistent_and_upsert_idempotent(tmp_path, monkeypatch):
    """重启后不该重新 embedding 全量知识，重复索引同 id 也不该报错退回关键词。"""
    import json

    import chromadb
    from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

    import agent.knowledge.knowledge_base as kbmod

    class _FakeEF(EmbeddingFunction[Documents]):
        def __init__(self):
            pass

        def __call__(self, input: Documents) -> Embeddings:
            return [[float(len(d) % 5), 1.0, 0.5] for d in input]

    monkeypatch.setattr(
        "chromadb.utils.embedding_functions.OpenAIEmbeddingFunction",
        lambda **kwargs: _FakeEF(),
    )
    monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "fake-key")
    monkeypatch.setattr(settings, "RAG_VECTOR_INDEX_PATH", str(tmp_path / "chroma"))

    data_dir = tmp_path / "knowledge"
    data_dir.mkdir()
    (data_dir / "holidays.json").write_text(
        json.dumps([{"keywords": ["端午"], "name": "端午节", "date": "06-19", "text": "端午节是6月19日至6月21日"}]),
        encoding="utf-8",
    )
    assert chromadb is not None and kbmod is not None  # 保持 import 显式

    first = KnowledgeBase(enable_vector=True)
    first._init_vector()  # 直接初始化向量层：warmup 会去读真实 data/，这里只针对临时目录
    first.load_data(str(data_dir))
    assert first.status()["vector_ready"] is True
    assert first.status()["chunks_in_index"] == 1

    # 模拟重启：新实例指向同一目录，重复 upsert 同 id 不得报错
    second = KnowledgeBase(enable_vector=True)
    second._init_vector()
    second.load_data(str(data_dir))
    assert second.status()["chunks_in_index"] == 1
    assert second.status()["vector_ready"] is True
