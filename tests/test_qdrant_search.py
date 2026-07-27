# tests/test_qdrant_search.py
"""유사도 검색 테스트.

임베딩은 monkeypatch로 대체하고, Qdrant는 in-memory 인스턴스를 쓴다.
실제 임베딩 차원(1536) 대신 4차원 벡터를 써서 테스트를 가볍게 유지한다.
"""
import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.taxonomy import LEVEL_TO_SUBCATEGORIES
from app.services import embedding_service, qdrant_service

TEST_COLLECTION = "test-search"
VECTOR_SIZE = 4

BEGINNER_SUB = LEVEL_TO_SUBCATEGORIES["초급"][0]
ADVANCED_SUB = LEVEL_TO_SUBCATEGORIES["고급"][0]

# 질의 벡터와의 코사인 유사도가 문서 순서대로 낮아지도록 구성한 샘플
DOCUMENTS = [
    # (id, vector, title, sub_category)
    (1, [1.0, 0.0, 0.0, 0.0], "useState", BEGINNER_SUB),
    (2, [0.9, 0.4, 0.0, 0.0], "useEffect", BEGINNER_SUB),
    (3, [0.5, 0.8, 0.0, 0.0], "Server Components", ADVANCED_SUB),
]

QUERY_VECTOR = [1.0, 0.0, 0.0, 0.0]


@pytest.fixture()
def search_client(monkeypatch):
    """in-memory Qdrant에 샘플 문서를 넣고 qdrant_service가 쓰도록 연결한다."""
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name=TEST_COLLECTION,
        vectors_config=qmodels.VectorParams(
            size=VECTOR_SIZE, distance=qmodels.Distance.COSINE),
    )
    client.upsert(
        collection_name=TEST_COLLECTION,
        points=[
            qmodels.PointStruct(
                id=doc_id,
                vector=vector,
                payload={
                    "text": f"{title} 설명 본문",
                    "title": title,
                    "source": f"/learn/{title.lower()}",
                    "sub_category": sub_category,
                },
            )
            for doc_id, vector, title, sub_category in DOCUMENTS
        ],
    )

    monkeypatch.setattr(qdrant_service, "qdrant_client", client)
    monkeypatch.setattr(qdrant_service, "COLLECTION_NAME", TEST_COLLECTION)
    monkeypatch.setattr(
        embedding_service, "embed_query", lambda text: QUERY_VECTOR)
    return client


def test_search_similar_returns_top_k(search_client):
    results = qdrant_service.search_similar("useState 알려줘", top_k=2)

    assert len(results) == 2


def test_search_similar_sorted_by_score_desc(search_client):
    results = qdrant_service.search_similar("useState 알려줘", top_k=3)

    scores = [result["score"] for result in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0]["title"] == "useState"


def test_search_similar_result_shape(search_client):
    results = qdrant_service.search_similar("useState 알려줘", top_k=1)

    assert set(results[0]) == {"text", "title", "source", "score"}
    assert results[0]["source"] == "/learn/usestate"


def test_search_similar_filters_by_level(search_client):
    results = qdrant_service.search_similar("질문", top_k=10, level="고급")

    assert [result["title"] for result in results] == ["Server Components"]


def test_search_similar_unknown_level_returns_empty(search_client):
    assert qdrant_service.search_similar("질문", level="왕초보") == []


def test_search_similar_empty_collection_returns_empty(monkeypatch):
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name=TEST_COLLECTION,
        vectors_config=qmodels.VectorParams(
            size=VECTOR_SIZE, distance=qmodels.Distance.COSINE),
    )
    monkeypatch.setattr(qdrant_service, "qdrant_client", client)
    monkeypatch.setattr(qdrant_service, "COLLECTION_NAME", TEST_COLLECTION)
    monkeypatch.setattr(
        embedding_service, "embed_query", lambda text: QUERY_VECTOR)

    assert qdrant_service.search_similar("질문") == []


def test_search_similar_returns_empty_on_error(monkeypatch):
    """검색이 실패해도 챗은 답변할 수 있어야 하므로 예외를 밖으로 던지지 않는다."""
    def _boom(text):
        raise embedding_service.EmbeddingError("임베딩 실패")

    monkeypatch.setattr(embedding_service, "embed_query", _boom)

    assert qdrant_service.search_similar("질문") == []
