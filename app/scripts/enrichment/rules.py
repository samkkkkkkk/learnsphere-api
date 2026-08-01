# backend/app/scripts/enrichment/rules.py
"""신규 문서(과거 큐레이션에 없는) 라벨을 결정적 규칙으로 부여.

규칙 기반 수동 매핑: 경로/파일명 → main_category, sub_category, topic_group.
어떤 규칙에도 걸리지 않으면 None을 반환해 파이프라인이 하드 실패하도록 한다
(silent 오라벨 방지).
"""

import re

from app.core import taxonomy
from app.scripts.enrichment import paths

# 신규 learn 7개 챕터 개요 페이지 → 레벨 sub_category (제안값)
_LEVEL_1 = taxonomy.LEVEL_TO_SUBCATEGORIES["초급"][0]  # "1단계: 사전 준비 ⚙️"
_LEVEL_2 = taxonomy.LEVEL_TO_SUBCATEGORIES["초급"][1]  # "2단계: 메인 학습 코스 (초급) 入门"

LEARN_LEVEL_BY_FILENAME = {
    "setup.md": _LEVEL_1,
    "creating-a-react-app.md": _LEVEL_1,
    "build-a-react-app-from-scratch.md": _LEVEL_1,
    "index.md": _LEVEL_1,
    "describing-the-ui.md": _LEVEL_2,
    "adding-interactivity.md": _LEVEL_2,
    "managing-state.md": _LEVEL_2,
}


def extract_title(content: str, source_path: str) -> str:
    """content frontmatter의 `title:`에서 추출, 없으면 파일명 stem으로 fallback."""
    parts = content.split("---", 2)
    if len(parts) > 2:
        m = re.search(r"title:\s*(.+)", parts[1])
        if m:
            title = m.group(1).strip()
            if title:
                return title
    # fallback: 파일명에서 확장자 제거 (title-less 문서 대응, seed.py KeyError 방지)
    stem = paths.filename(source_path)
    return re.sub(r"\.md$", "", stem)


def label_for(source_path: str, content: str):
    """신규 문서 라벨 dict 반환. 규칙 미적용 시 None."""
    section = paths.top_section(source_path)

    if section == "learn":
        level = LEARN_LEVEL_BY_FILENAME.get(paths.filename(source_path))
        if level is None:
            return None
        return {
            "source_path": source_path,
            "title": extract_title(content, source_path),
            "main_category": taxonomy.MAIN_CATEGORIES["learn"],
            "sub_category": level,
            "topic_group": None,
        }

    if section == "reference":
        sub = paths.reference_subsection(source_path)
        sub_category = taxonomy.REFERENCE_SUBCATEGORIES.get(sub)
        if sub_category is None:
            return None
        return {
            "source_path": source_path,
            "title": extract_title(content, source_path),
            "main_category": taxonomy.MAIN_CATEGORIES["reference"],
            "sub_category": sub_category,
            "topic_group": None,
        }

    # learn/reference 외(blog/warnings 등)는 이 파이프라인 대상 아님
    return None
