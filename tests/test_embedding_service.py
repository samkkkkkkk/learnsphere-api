# tests/test_embedding_service.py
"""임베딩 서비스 테스트. OpenAI 클라이언트는 가짜 객체로 대체한다."""
import pytest

from app.services import embedding_service


class _FakeEmbeddingItem:
    def __init__(self, index: int, embedding):
        self.index = index
        self.embedding = embedding


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeEmbeddings:
    """호출 인자를 기록하고 입력 개수만큼 벡터를 돌려주는 스텁."""

    def __init__(self, recorder, shuffle=False):
        self._recorder = recorder
        self._shuffle = shuffle

    def create(self, input, model):  # noqa: A002 — OpenAI SDK의 인자 이름
        self._recorder.append({"input": list(input), "model": model})
        items = [
            _FakeEmbeddingItem(i, [float(len(text))] * 3)
            for i, text in enumerate(input)
        ]
        # API가 순서를 뒤섞어 반환하는 상황을 재현한다
        return _FakeResponse(list(reversed(items)) if self._shuffle else items)


class _FakeClient:
    def __init__(self, recorder, shuffle=False):
        self.embeddings = _FakeEmbeddings(recorder, shuffle)


@pytest.fixture()
def calls(monkeypatch):
    recorder = []
    monkeypatch.setattr(
        embedding_service, "_get_client", lambda: _FakeClient(recorder))
    return recorder


def test_embed_texts_batches_by_100(calls):
    texts = [f"doc-{i}" for i in range(250)]

    vectors = embedding_service.embed_texts(texts)

    assert len(calls) == 3  # 100 + 100 + 50
    assert [len(call["input"]) for call in calls] == [100, 100, 50]
    assert len(vectors) == 250


def test_embed_texts_preserves_order(monkeypatch):
    """API가 순서를 섞어 반환해도 입력 순서대로 정렬해야 한다."""
    recorder = []
    monkeypatch.setattr(
        embedding_service, "_get_client",
        lambda: _FakeClient(recorder, shuffle=True))

    # 길이가 서로 다른 텍스트 → 벡터 값으로 순서를 식별할 수 있다
    vectors = embedding_service.embed_texts(["a", "bb", "ccc"])

    assert [vector[0] for vector in vectors] == [1.0, 2.0, 3.0]


def test_embed_texts_empty_input_returns_empty(calls):
    assert embedding_service.embed_texts([]) == []
    assert calls == []  # API를 호출하지 않는다


def test_embed_query_returns_single_vector(calls):
    vector = embedding_service.embed_query("useEffect 정리 함수")

    assert isinstance(vector, list)
    assert vector == [len("useEffect 정리 함수")] * 3
    assert calls[0]["model"] == embedding_service.EMBEDDING_MODEL


def test_embed_texts_wraps_api_error(monkeypatch):
    class _BoomEmbeddings:
        def create(self, input, model):  # noqa: A002
            raise RuntimeError("rate limit")

    class _BoomClient:
        embeddings = _BoomEmbeddings()

    monkeypatch.setattr(embedding_service, "_get_client", lambda: _BoomClient())

    with pytest.raises(embedding_service.EmbeddingError):
        embedding_service.embed_texts(["x"])
