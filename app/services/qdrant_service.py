# backend/app/services/qdrant_service.py

import os
from qdrant_client import QdrantClient
from typing import Dict

# --- 설정 ---
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "react-docs-complete"

# --- Qdrant 클라이언트 초기화 ---
qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def get_contexts_by_level(level: str) -> Dict[str, str]:
    """
    주어진 레벨에 해당하는 모든 토픽과 그 컨텍스트를 Qdrant에서 가져옵니다.

    Args:
        level (str): "초급", "중급", "고급" 중 하나.

    Returns:
        Dict[str, str]: {'토픽 제목': '관련 문서 내용 전체'} 형태의 딕셔너리.
    """
    print(f"  > [Qdrant] '{level}' 레벨의 모든 컨텍스트 검색 시작...")

    level_mapping = {
        "초급": ["1단계: 사전 준비 ⚙️", "2단계: 메인 학습 코스 (초급) 入门"],
        "중급": ["3단계: 메인 학습 코스 (중급) 🚀"],
        "고급": ["4단계: 심화 탐구 🧠"]
    }
    target_sub_categories = level_mapping.get(level)

    if not target_sub_categories:
        print(f"  > [Qdrant] 오류: 유효하지 않은 레벨입니다: {level}")
        return {}

    try:
        # Qdrant에서 모든 문서를 스크롤하여 가져옵니다.
        # 실제 프로덕션에서는 더 효율적인 필터링 방법을 고려할 수 있습니다.
        scrolled_points, _ = qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            limit=2000, # 전체 문서 개수에 맞게 조절
            with_payload=True
        )

        # 토픽(title)별로 텍스트 조각(context)을 그룹화합니다.
        lessons_by_title: Dict[str, list] = {}
        for point in scrolled_points:
            payload = point.payload
            sub_category = payload.get('sub_category')
            title = payload.get('title')
            
            if sub_category in target_sub_categories and title:
                if title not in lessons_by_title:
                    lessons_by_title[title] = []
                lessons_by_title[title].append(payload.get('text', ''))

        # 그룹화된 텍스트 조각들을 하나의 긴 컨텍스트 문자열로 합칩니다.
        final_contexts = {}
        for title, texts in lessons_by_title.items():
            final_contexts[title] = "\n\n---\n\n".join(texts)
            
        print(f"  > [Qdrant] '{level}' 레벨에서 {len(final_contexts)}개의 토픽 컨텍스트를 성공적으로 가져왔습니다.")
        return final_contexts

    except Exception as e:
        print(f"  > [Qdrant] 오류 발생: {e}")
        return {}
