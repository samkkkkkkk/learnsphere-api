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


# --- 토큰 한도 (OpenAI는 8192 초과 시 400을 던진다) ---

def test_split_returns_original_when_within_limit():
    assert embedding_service.split_text_by_tokens("짧은 글") == ["짧은 글"]


def test_split_keeps_every_piece_within_limit():
    # 문단 여러 개로 이루어진 긴 텍스트
    text = "\n\n".join([f"문단 {i} " + "React 상태 관리 " * 50 for i in range(40)])

    pieces = embedding_service.split_text_by_tokens(text, max_tokens=500)

    assert len(pieces) > 1
    assert all(embedding_service.count_tokens(p) <= 500 for p in pieces)


def test_split_hard_splits_single_oversized_paragraph():
    """문단 경계가 없어도 한도를 지켜야 한다."""
    text = "리액트 " * 3000  # 빈 줄 없는 한 덩어리

    pieces = embedding_service.split_text_by_tokens(text, max_tokens=200)

    assert len(pieces) > 1
    assert all(embedding_service.count_tokens(p) <= 200 for p in pieces)


def test_split_counts_paragraph_separators():
    """문단을 도로 이을 때 들어가는 \\n\\n 토큰까지 예산에 넣어야 한도가 지켜진다."""
    # 짧은 문단이 많이 쌓이는 경우 — 구분자 누적을 빼먹으면 한도를 넘는다
    text = "\n\n".join("가" for _ in range(300))

    pieces = embedding_service.split_text_by_tokens(text, max_tokens=30)

    assert all(embedding_service.count_tokens(p) <= 30 for p in pieces)


def test_split_preserves_content():
    text = "\n\n".join(f"단락{i}" for i in range(200))

    joined = "".join(embedding_service.split_text_by_tokens(text, max_tokens=50))

    # 조각을 이으면 원문의 모든 단락이 남아 있어야 한다
    for i in range(200):
        assert f"단락{i}" in joined


def test_embed_texts_rejects_oversized_input(calls):
    """호출자가 쪼개지 않고 넘기면 API 400 대신 명확한 오류를 낸다."""
    huge = "리액트 " * 10000

    with pytest.raises(embedding_service.EmbeddingError, match="토큰"):
        embedding_service.embed_texts([huge])

    assert calls == []  # API를 호출하지 않는다


def test_embed_texts_batches_by_token_budget(calls, monkeypatch):
    """개수 한도에 안 걸려도 토큰 총량이 크면 요청을 나눈다."""
    monkeypatch.setattr(embedding_service, "MAX_TOKENS_PER_REQUEST", 1000)
    texts = [("React " * 100) for _ in range(10)]  # 각 100 토큰 남짓

    embedding_service.embed_texts(texts)

    assert len(calls) > 1
    for call in calls:
        total = sum(embedding_service.count_tokens(t) for t in call["input"])
        assert total <= 1000 or len(call["input"]) == 1


def test_embed_query_truncates_instead_of_failing(calls):
    """질의가 한도를 넘어도 오류 대신 앞부분으로 검색을 이어간다."""
    huge_query = "리액트 " * 10000

    embedding_service.embed_query(huge_query)

    assert len(calls) == 1
    assert embedding_service.count_tokens(calls[0]["input"][0]) \
        <= embedding_service.MAX_TOKENS_PER_INPUT


def test_embed_texts_wraps_api_error(monkeypatch):
    class _BoomEmbeddings:
        def create(self, input, model):  # noqa: A002
            raise RuntimeError("rate limit")

    class _BoomClient:
        embeddings = _BoomEmbeddings()

    monkeypatch.setattr(embedding_service, "_get_client", lambda: _BoomClient())

    with pytest.raises(embedding_service.EmbeddingError):
        embedding_service.embed_texts(["x"])
