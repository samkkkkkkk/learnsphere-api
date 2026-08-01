# backend/app/scripts/enrichment/extract_curated_labels.py
"""git 커밋 0febce2의 과거 가공본에서 사람이 큐레이션한 라벨을 추출.

`content`(대용량 원문)를 제외한 5개 라벨 필드만 뽑아 `curated_labels.json`으로
저장한다. 키는 정규화된 source_path. 일회성 자산 생성용이며, 산출물은 커밋되어
이후 가공은 git 이력 없이도 재현 가능하다.

실행: uv run python -m app.scripts.enrichment.extract_curated_labels
"""

import json
import os
import subprocess

from app.scripts.enrichment.paths import normalize_source

SOURCE_COMMIT = "0febce2"
SOURCE_FILE = "react_complete_learning_data.json"
LABEL_FIELDS = ("title", "main_category", "sub_category", "topic_group")

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "curated_labels.json")


def extract() -> dict:
    raw = subprocess.run(
        ["git", "show", f"{SOURCE_COMMIT}:{SOURCE_FILE}"],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    docs = json.loads(raw)

    labels = {}
    for doc in docs:
        key = normalize_source(doc["source_path"])
        labels[key] = {
            "source_path": key,
            **{f: doc.get(f) for f in LABEL_FIELDS},
        }
    return labels


def main():
    labels = extract()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"추출 완료: {len(labels)}개 라벨 → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
