# backend/tests/test_enrichment.py
"""가공 파이프라인 회귀·단위 테스트.

원래 앱을 망가뜨린 실패 유형을 정면으로 겨냥한다:
  - 빈 sub_category → 레벨 필터가 아무것도 못 잡음 (P1-1)
  - 택소노미 문자열 불일치 (이모지 variation selector, CJK) (P1-2)
  - 빈 title → seed.py KeyError (P1-3)
"""

import json
import re
import subprocess

import pytest

from app.core import taxonomy
from app.scripts import enrich_learning_data as enr
from app.scripts.enrichment import rules, paths


@pytest.fixture(scope="module")
def curated():
    return enr.load_curated()


@pytest.fixture(scope="module")
def enriched():
    return enr.enrich()


# --- 스키마 / 카운트 ---

def test_document_count(enriched):
    assert len(enriched) == 141


def test_blog_warnings_excluded(enriched):
    for d in enriched:
        assert "/blog/" not in d["source_path"]
        assert "/warnings/" not in d["source_path"]


def test_curated_and_rule_split(enriched, curated):
    from_curated = [d for d in enriched if d["source_path"] in curated]
    from_rules = [d for d in enriched if d["source_path"] not in curated]
    assert len(from_curated) == 95
    assert len(from_rules) == 46


def test_curated_labels_recovered(enriched, curated):
    """복원된 95개 라벨이 curated_labels.json과 정확 일치 (회귀 방지)."""
    for d in enriched:
        if d["source_path"] in curated:
            gold = curated[d["source_path"]]
            for field in ("title", "main_category", "sub_category", "topic_group"):
                assert d[field] == gold[field], f"{field} 불일치: {d['source_path']}"


def test_required_fields_non_empty(enriched):
    for d in enriched:
        for field in enr.REQUIRED_NON_EMPTY:
            assert d.get(field), f"{field} 빈값: {d.get('source_path')}"


def test_source_path_normalized_and_unique(enriched):
    seen = set()
    for d in enriched:
        sp = d["source_path"]
        assert "\\" not in sp
        assert sp == sp.lower()
        assert sp not in seen
        seen.add(sp)


# --- P1-3: title ---

def test_all_titles_non_empty(enriched):
    for d in enriched:
        assert d["title"].strip()


def test_title_fallback_for_frontmatterless_docs(enriched):
    """frontmatter title 없는 react-dom 컴포넌트 4개도 non-empty (fallback)."""
    targets = [
        "src/content/reference/react-dom/components/link.md",
        "src/content/reference/react-dom/components/meta.md",
        "src/content/reference/react-dom/components/script.md",
        "src/content/reference/react-dom/components/style.md",
    ]
    by_path = {d["source_path"]: d for d in enriched}
    for t in targets:
        assert t in by_path, f"대상 문서 누락: {t}"
        assert by_path[t]["title"].strip()


# --- P1-1: 레벨 필터 회귀 (원래 버그 정면 방어) ---

def test_level_filter_returns_docs(enriched):
    """각 레벨(초급/중급/고급)이 sub_category 필터로 non-empty 결과."""
    for level, targets in taxonomy.LEVEL_TO_SUBCATEGORIES.items():
        matched = [d for d in enriched if d["sub_category"] in targets]
        assert matched, f"레벨 '{level}' 매칭 문서 0개 (레벨 필터 무력화)"


# --- P1-2: 택소노미 바이트 일치 ---

def test_taxonomy_matches_qdrant_service_source():
    """taxonomy.LEVEL_TO_SUBCATEGORIES == qdrant_service 사용값 (드리프트 방지)."""
    src = open("app/services/qdrant_service.py", encoding="utf-8").read()
    assert "LEVEL_TO_SUBCATEGORIES" in src  # 상수 참조 사용 확인
    # qdrant_service가 taxonomy를 import해 쓰므로 런타임 값 동일성 확인
    from app.services import qdrant_service  # noqa: F401 (import 부작용 없이 로드)
    assert qdrant_service.LEVEL_TO_SUBCATEGORIES is taxonomy.LEVEL_TO_SUBCATEGORIES


def test_taxonomy_matches_curated_data(curated):
    """taxonomy 상수가 실제 데이터(curated) sub_category와 바이트 동일."""
    data_subs = {v["sub_category"] for v in curated.values()}
    # 레벨 4종 + 참조 2종이 모두 데이터에 실재 (정확 일치)
    assert set(taxonomy.LEARN_SUBCATEGORIES) <= data_subs
    assert taxonomy.REFERENCE_SUBCATEGORIES["react"] in data_subs
    assert taxonomy.REFERENCE_SUBCATEGORIES["react-dom"] in data_subs


def test_gear_emoji_has_variation_selector():
    """'1단계' 문자열이 U+FE0F를 포함하는지 (바이트 정밀도 회귀)."""
    level1 = taxonomy.LEVEL_TO_SUBCATEGORIES["초급"][0]
    assert "⚙️" in level1


# --- P2-4: 결정성 ---

def test_idempotent():
    a = json.dumps(enr.enrich(), ensure_ascii=False, sort_keys=True)
    b = json.dumps(enr.enrich(), ensure_ascii=False, sort_keys=True)
    assert a == b


# --- P2-6: fail-loud ---

def test_validate_rejects_empty_field():
    bad = [{"content": "x", "title": "", "main_category": taxonomy.MAIN_CATEGORIES["learn"],
            "sub_category": taxonomy.LEARN_SUBCATEGORIES[0], "source_path": "a"}]
    with pytest.raises(ValueError):
        enr.validate(bad)


def test_validate_rejects_unknown_subcategory():
    bad = [{"content": "x", "title": "t", "main_category": taxonomy.MAIN_CATEGORIES["learn"],
            "sub_category": "존재하지-않는-카테고리", "source_path": "a"}]
    with pytest.raises(ValueError):
        enr.validate(bad)


def test_build_enriched_hard_fails_on_unlabeled():
    raw = [{"source": "src/content/learn/unknown-doc-xyz.md", "content": "---\ntitle: X\n---\nbody"}]
    with pytest.raises(ValueError, match="하드 실패"):
        enr.build_enriched(raw, curated={})


# --- P2-7: rules 단위 테스트 ---

@pytest.mark.parametrize("path,expected_sub", [
    ("src/content/reference/react/use-state.md", "React 핵심 API"),
    ("src/content/reference/react-dom/create-portal.md", "React DOM API"),
    ("src/content/reference/rsc/server-components.md", "React Server Components"),
    ("src/content/reference/rules/rules-of-hooks.md", "React 규칙"),
])
def test_rules_reference_mapping(path, expected_sub):
    label = rules.label_for(path, "---\ntitle: T\n---\nbody")
    assert label is not None
    assert label["sub_category"] == expected_sub
    assert label["main_category"] == taxonomy.MAIN_CATEGORIES["reference"]


@pytest.mark.parametrize("filename,expected_sub", [
    ("setup.md", taxonomy.LEVEL_TO_SUBCATEGORIES["초급"][0]),
    ("managing-state.md", taxonomy.LEVEL_TO_SUBCATEGORIES["초급"][1]),
])
def test_rules_learn_level_mapping(filename, expected_sub):
    path = f"src/content/learn/{filename}"
    label = rules.label_for(path, "---\ntitle: T\n---\nbody")
    assert label["sub_category"] == expected_sub


def test_rules_returns_none_for_blog():
    assert rules.label_for("src/content/blog/2023.md", "x") is None


def test_extract_title_fallback():
    # frontmatter title 없음 → 파일명 stem
    title = rules.extract_title("no frontmatter here", "src/content/reference/react-dom/components/link.md")
    assert title == "link"


def test_extract_title_from_frontmatter():
    title = rules.extract_title("---\ntitle: 훅 사용하기\n---\nbody", "x/y.md")
    assert title == "훅 사용하기"


# --- P2-5: 검색 관련성 (in-memory Qdrant, 실 클러스터 미접촉) ---

@pytest.mark.slow
def test_search_relevance(enriched):
    import uuid
    from qdrant_client import QdrantClient, models
    from sentence_transformers import SentenceTransformer

    target = "src/content/learn/add-react-to-an-existing-project.md"
    by_path = {d["source_path"]: d for d in enriched}
    assert target in by_path

    # index_data.py와 동일한 청킹으로 소규모 샘플만 임베딩
    sample_docs = [by_path[target]] + [d for d in enriched if d["source_path"] != target][:14]
    model = SentenceTransformer("distiluse-base-multilingual-cased-v1")
    points = []
    for d in sample_docs:
        parts = d["content"].split("---", 2)
        body = parts[2].strip() if len(parts) > 2 else d["content"].strip()
        section = body.split("\n## ")[0].strip() or body[:500]
        text = f"제목: {d['title']}\n\n{section}"
        points.append(models.PointStruct(
            id=str(uuid.uuid4()),
            vector=model.encode(text).tolist(),
            payload={"source": d["source_path"]},
        ))

    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="t",
        vectors_config=models.VectorParams(size=model.get_sentence_embedding_dimension(),
                                           distance=models.Distance.COSINE),
    )
    client.upload_points(collection_name="t", points=points, wait=True)
    hits = client.query_points(
        collection_name="t",
        query=model.encode("기존 프로젝트에 React를 추가하는 방법").tolist(),
        limit=3,
    ).points
    assert hits[0].payload["source"] == target
