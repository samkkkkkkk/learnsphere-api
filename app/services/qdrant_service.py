# backend/app/services/qdrant_service.py

import os
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from typing import Dict, List, Optional

from ..core.taxonomy import LEVEL_TO_SUBCATEGORIES
from . import embedding_service

# --- 설정 ---
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
# 인덱싱 스크립트(index_data.py)와 동일한 환경 변수를 공유합니다.
# 기본값은 OpenAI 임베딩(1536차원)으로 재인덱싱한 신규 컬렉션. 구 컬렉션
# react-docs-complete(sentence-transformers 384차원)는 호환되지 않는다.
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "react-docs-openai")

# --- Qdrant 클라이언트 초기화 ---
qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def _level_filter(level: str) -> Optional[qmodels.Filter]:
    """레벨에 해당하는 sub_category 필터를 만든다. 알 수 없는 레벨이면 None."""
    target_sub_categories = LEVEL_TO_SUBCATEGORIES.get(level)
    if not target_sub_categories:
        return None

    return qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="sub_category",
                match=qmodels.MatchAny(any=target_sub_categories),
            )
        ]
    )


def search_similar(query: str, top_k: int = 5,
                   level: Optional[str] = None) -> List[Dict]:
    """질문과 의미가 가까운 문서 조각을 top_k개 반환합니다.

    파이프라인이 쓰는 get_contexts_by_level이 레벨 전량을 훑는 것과 달리,
    이쪽은 질의 임베딩 기반의 유사도 검색입니다. 튜터 챗이 사용합니다.

    Args:
        query: 사용자 질문.
        top_k: 가져올 문서 조각 수.
        level: 지정하면 해당 레벨의 문서로만 한정합니다.

    Returns:
        [{'text', 'title', 'source', 'score'}] — 점수 내림차순. 실패 시 빈 리스트.
    """
    query_filter = None
    if level is not None:
        query_filter = _level_filter(level)
        if query_filter is None:
            print(f"  > [Qdrant] 오류: 유효하지 않은 레벨입니다: {level}")
            return []

    try:
        vector = embedding_service.embed_query(query)
        response = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
    except Exception as e:
        # 검색이 실패해도 챗 자체는 답변할 수 있어야 하므로 빈 결과로 축약한다.
        print(f"  > [Qdrant] 유사도 검색 실패: {e}")
        return []

    results = []
    for point in response.points:
        payload = point.payload or {}
        results.append({
            "text": payload.get("text", ""),
            "title": payload.get("title", ""),
            "source": payload.get("source", ""),
            "score": point.score,
        })
    return results


def get_contexts_by_level(level: str) -> Dict[str, str]:
    """
    주어진 레벨에 해당하는 모든 토픽과 그 컨텍스트를 Qdrant에서 가져옵니다.

    Args:
        level (str): "초급", "중급", "고급" 중 하나.

    Returns:
        Dict[str, str]: {'토픽 제목': '관련 문서 내용 전체'} 형태의 딕셔너리.
    """
    print(f"  > [Qdrant] '{level}' 레벨의 모든 컨텍스트 검색 시작...")

    # sub_category를 서버 사이드에서 필터링하고, 페이지네이션으로 전체를 순회합니다.
    scroll_filter = _level_filter(level)

    if scroll_filter is None:
        print(f"  > [Qdrant] 오류: 유효하지 않은 레벨입니다: {level}")
        return {}

    try:
        lessons_by_title: Dict[str, list] = {}
        offset = None
        while True:
            points, offset = qdrant_client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=scroll_filter,
                limit=256,
                offset=offset,
                with_payload=True,
            )
            for point in points:
                payload = point.payload or {}
                title = payload.get('title')
                if title:
                    lessons_by_title.setdefault(title, []).append(payload.get('text', ''))
            if offset is None:
                break

        # 그룹화된 텍스트 조각들을 하나의 긴 컨텍스트 문자열로 합칩니다.
        final_contexts = {}
        for title, texts in lessons_by_title.items():
            final_contexts[title] = "\n\n---\n\n".join(texts)

        print(f"  > [Qdrant] '{level}' 레벨에서 {len(final_contexts)}개의 토픽 컨텍스트를 성공적으로 가져왔습니다.")
        return final_contexts

    except Exception as e:
        print(f"  > [Qdrant] 오류 발생: {e}")
        return {}
