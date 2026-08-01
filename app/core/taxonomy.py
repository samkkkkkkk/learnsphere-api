# backend/app/core/taxonomy.py
"""가공 파이프라인과 검색 서비스가 공유하는 정본(定本) 택소노미.

레벨 검색(`qdrant_service.get_contexts_by_level`)이 사용하는 `sub_category`
문자열은 데이터에 저장된 값과 **바이트 단위로 정확히 일치**해야 한다(이모지의
variation selector U+FE0F, CJK `入门` 포함). 문자열 출처를 이 파일 한 곳으로
단일화해 드리프트를 구조적으로 차단한다.
"""

# 학습 레벨(초급/중급/고급) → 해당 sub_category 값. qdrant_service의 서버사이드
# 필터가 이 매핑을 사용한다.
LEVEL_TO_SUBCATEGORIES = {
    "초급": ["1단계: 사전 준비 ⚙️", "2단계: 메인 학습 코스 (초급) 入门"],
    "중급": ["3단계: 메인 학습 코스 (중급) 🚀"],
    "고급": ["4단계: 심화 탐구 🧠"],
}

# 정본 main_category (경로 learn/reference에서 부여)
MAIN_CATEGORIES = {
    "learn": "학습 과정 (Learn)",
    "reference": "API 레퍼런스 (Reference)",
}

# 레벨 검색이 커버하는 학습 코스 sub_category (LEVEL_TO_SUBCATEGORIES의 평탄화)
LEARN_SUBCATEGORIES = [sc for values in LEVEL_TO_SUBCATEGORIES.values() for sc in values]

# 저장은 되지만 레벨 검색 대상이 아닌 참조(reference) sub_category
REFERENCE_SUBCATEGORIES = {
    "react": "React 핵심 API",
    "react-dom": "React DOM API",
    # 과거 가공본에 없던 신규 경로 — 제안값(레벨 검색 비대상이라 안전)
    "rsc": "React Server Components",
    "rules": "React 규칙",
}

# 산출물 검증에 쓰는 전체 유효 sub_category 집합
SUB_CATEGORIES = set(LEARN_SUBCATEGORIES) | set(REFERENCE_SUBCATEGORIES.values())
