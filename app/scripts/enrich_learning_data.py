# backend/app/scripts/enrich_learning_data.py
"""가공 파이프라인: raw React 문서 → 라벨링된 학습 데이터.

raw(`react_docs_data.json`, source+content)에 `main_category`/`sub_category`(학습레벨)
/`title`/`source_path`/`topic_group`을 부여해 소비처(`index_data.py`,`seed.py`)가
읽는 `react_complete_learning_data.json`을 생성한다.

라벨 출처 우선순위:
  1. `curated_labels.json` (git 0febce2에서 복원한 사람 큐레이션, 95개)
  2. `rules.py` 규칙 기반 매핑 (신규 learn/reference 46개)
blog/warnings는 레벨 커리큘럼 대상이 아니라 제외 → 최종 141개.

실행: uv run python -m app.scripts.enrich_learning_data
"""

import json
import os

from app.core import taxonomy
from app.scripts.enrichment import paths, rules

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW_PATH = os.path.join(BASE_DIR, "react_docs_data.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "react_complete_learning_data.json")
CURATED_PATH = os.path.join(os.path.dirname(__file__), "enrichment", "curated_labels.json")

IN_SCOPE_SECTIONS = {"learn", "reference"}
REQUIRED_NON_EMPTY = ("content", "title", "main_category", "sub_category", "source_path")


def load_raw(path: str = RAW_PATH) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_curated(path: str = CURATED_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_enriched(raw_docs: list, curated: dict) -> list:
    """raw 문서 목록 → 가공된 문서 목록. 규칙 미적용 문서는 예외로 중단."""
    enriched = []
    unlabeled = []
    for doc in raw_docs:
        source_path = paths.normalize_source(doc["source"])
        if paths.top_section(source_path) not in IN_SCOPE_SECTIONS:
            continue  # blog/warnings 제외

        content = doc["content"]
        if source_path in curated:
            label = dict(curated[source_path])
            label["source_path"] = source_path
        else:
            label = rules.label_for(source_path, content)
            if label is None:
                unlabeled.append(source_path)
                continue

        label["content"] = content
        enriched.append(label)

    if unlabeled:
        raise ValueError(
            f"라벨 규칙에 걸리지 않은 문서 {len(unlabeled)}개(하드 실패): "
            + ", ".join(unlabeled)
        )
    return enriched


def validate(docs: list) -> None:
    """산출물 스키마 검증. 위반 시 예외."""
    seen_paths = set()
    for d in docs:
        for field in REQUIRED_NON_EMPTY:
            if not d.get(field):
                raise ValueError(f"필수 필드 '{field}' 누락/빈값: {d.get('source_path')}")
        if d["sub_category"] not in taxonomy.SUB_CATEGORIES:
            raise ValueError(
                f"미정의 sub_category '{d['sub_category']}': {d['source_path']}"
            )
        if d["main_category"] not in taxonomy.MAIN_CATEGORIES.values():
            raise ValueError(
                f"미정의 main_category '{d['main_category']}': {d['source_path']}"
            )
        if d["source_path"] in seen_paths:
            raise ValueError(f"source_path 중복: {d['source_path']}")
        seen_paths.add(d["source_path"])


def enrich(raw_path: str = RAW_PATH, curated_path: str = CURATED_PATH) -> list:
    docs = build_enriched(load_raw(raw_path), load_curated(curated_path))
    validate(docs)
    return docs


def main():
    docs = enrich()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)
    print(f"가공 완료: {len(docs)}개 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
