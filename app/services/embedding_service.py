# app/services/embedding_service.py
"""OpenAI 임베딩 생성.

인덱싱 스크립트(index_data.py)와 검색(qdrant_service.search_similar)이 공유한다.
sentence-transformers를 쓰던 시절에는 서빙 프로세스가 수백 MB짜리 모델을 로드해야
했지만, API 호출로 바꾸면서 그 부담이 사라졌다.

다만 로컬 모델은 긴 입력을 조용히 잘라냈던 반면 OpenAI API는 8192 토큰을 넘으면
400을 반환한다. 그래서 여기서 토큰 수를 직접 세고, 한도를 넘는 입력은 호출자가
미리 쪼개도록 강제한다.
"""
import os
from typing import List, Sequence

import tiktoken
from openai import OpenAI

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# text-embedding-3-small의 출력 차원. Qdrant 컬렉션 생성 시 이 값을 쓴다.
EMBEDDING_DIMENSION = 1536

# 입력 하나의 최대 토큰. API 한도는 8192이므로 여유를 둔다.
MAX_TOKENS_PER_INPUT = 8000

# 한 요청에 실어 보낼 텍스트 개수와 토큰 총량 상한.
# 개수만 제한하면 긴 청크가 몰릴 때 요청 단위 토큰 한도에 걸린다.
BATCH_SIZE = 100
MAX_TOKENS_PER_REQUEST = 250_000


class EmbeddingError(Exception):
    """임베딩 생성 실패."""


_client: OpenAI | None = None
_encoding: "tiktoken.Encoding | None" = None


def _get_client() -> OpenAI:
    """OpenAI 클라이언트를 지연 생성한다 (import 시점에 키를 요구하지 않도록)."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def _get_encoding() -> "tiktoken.Encoding":
    global _encoding
    if _encoding is None:
        try:
            _encoding = tiktoken.encoding_for_model(EMBEDDING_MODEL)
        except KeyError:
            # 모델명이 tiktoken 매핑에 없으면 OpenAI 최신 계열의 기본 인코딩을 쓴다
            _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding


def count_tokens(text: str) -> int:
    return len(_get_encoding().encode(text))


def split_text_by_tokens(text: str,
                         max_tokens: int = MAX_TOKENS_PER_INPUT) -> List[str]:
    """텍스트를 max_tokens 이하 조각들로 나눈다.

    문단(빈 줄) 경계를 우선 지키고, 문단 하나가 한도를 넘을 때만 토큰 단위로
    강제 분할한다. 한도 이하면 원문을 그대로 담은 1개짜리 리스트를 반환한다.
    """
    if not text:
        return []
    if count_tokens(text) <= max_tokens:
        return [text]

    encoding = _get_encoding()
    separator = "\n\n"
    # 문단을 도로 이을 때 들어가는 구분자도 예산에 넣어야 한도가 보장된다
    separator_tokens = len(encoding.encode(separator))

    pieces: List[str] = []
    buffer: List[str] = []
    buffer_tokens = 0

    for paragraph in text.split(separator):
        paragraph_tokens = len(encoding.encode(paragraph))

        if paragraph_tokens > max_tokens:
            # 문단 하나로도 한도를 넘으면 토큰 단위로 잘라낸다
            if buffer:
                pieces.append(separator.join(buffer))
                buffer, buffer_tokens = [], 0
            tokens = encoding.encode(paragraph)
            for start in range(0, len(tokens), max_tokens):
                pieces.append(encoding.decode(tokens[start:start + max_tokens]))
            continue

        added_tokens = paragraph_tokens + (separator_tokens if buffer else 0)
        if buffer and buffer_tokens + added_tokens > max_tokens:
            pieces.append(separator.join(buffer))
            buffer, buffer_tokens = [], 0
            added_tokens = paragraph_tokens

        buffer.append(paragraph)
        buffer_tokens += added_tokens

    if buffer:
        pieces.append(separator.join(buffer))

    return pieces


def _iter_batches(texts: Sequence[str]):
    """개수와 토큰 총량을 모두 만족하는 배치로 나눈다."""
    batch: List[str] = []
    batch_tokens = 0

    for text in texts:
        tokens = count_tokens(text)
        if tokens > MAX_TOKENS_PER_INPUT:
            raise EmbeddingError(
                f"입력 하나가 최대 {MAX_TOKENS_PER_INPUT} 토큰을 초과합니다({tokens} 토큰). "
                f"split_text_by_tokens()로 먼저 쪼개세요.")

        if batch and (len(batch) >= BATCH_SIZE
                      or batch_tokens + tokens > MAX_TOKENS_PER_REQUEST):
            yield batch
            batch, batch_tokens = [], 0

        batch.append(text)
        batch_tokens += tokens

    if batch:
        yield batch


def embed_texts(texts: Sequence[str]) -> List[List[float]]:
    """여러 텍스트를 임베딩한다. 입력 순서가 그대로 유지된다."""
    if not texts:
        return []

    vectors: List[List[float]] = []
    for batch in _iter_batches(texts):
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
    """검색 질의 하나를 임베딩한다.

    질의가 한도를 넘는 경우는 사실상 없지만, 그럴 때 오류를 내기보다
    앞부분만 써서 검색을 계속하는 편이 낫다.
    """
    pieces = split_text_by_tokens(text)
    if not pieces:
        raise EmbeddingError("빈 질의는 임베딩할 수 없습니다.")

    vectors = embed_texts(pieces[:1])
    if not vectors:
        raise EmbeddingError("질의 임베딩 결과가 비어있습니다.")
    return vectors[0]
