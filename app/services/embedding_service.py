# app/services/embedding_service.py
"""OpenAI 임베딩 생성.

인덱싱 스크립트(index_data.py)와 검색(qdrant_service.search_similar)이 공유한다.
sentence-transformers를 쓰던 시절에는 서빙 프로세스가 수백 MB짜리 모델을 로드해야
했지만, API 호출로 바꾸면서 그 부담이 사라졌다.
"""
import os
from typing import List, Sequence

from openai import OpenAI

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# text-embedding-3-small의 출력 차원. Qdrant 컬렉션 생성 시 이 값을 쓴다.
EMBEDDING_DIMENSION = 1536

# 한 번의 API 호출에 실어 보낼 텍스트 개수.
BATCH_SIZE = 100


class EmbeddingError(Exception):
    """임베딩 생성 실패."""


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """OpenAI 클라이언트를 지연 생성한다 (import 시점에 키를 요구하지 않도록)."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def embed_texts(texts: Sequence[str]) -> List[List[float]]:
    """여러 텍스트를 임베딩한다. 입력 순서가 그대로 유지된다."""
    if not texts:
        return []

    vectors: List[List[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = list(texts[start:start + BATCH_SIZE])
        try:
            response = _get_client().embeddings.create(
                input=batch, model=EMBEDDING_MODEL)
        except Exception as e:
            raise EmbeddingError(f"임베딩 생성 중 오류: {e}") from e

        # API가 순서를 보장하지만, index로 정렬해 한 번 더 확실히 한다.
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors.extend(item.embedding for item in ordered)

    return vectors


def embed_query(text: str) -> List[float]:
    """검색 질의 하나를 임베딩한다."""
    vectors = embed_texts([text])
    if not vectors:
        raise EmbeddingError("질의 임베딩 결과가 비어있습니다.")
    return vectors[0]
