# 가공 파이프라인 재구축 — 단계별 상세 계획 (detail_plan)

> 원칙: **가장 단순하게 동작하는 것부터** 만들고, 각 Phase마다 검증을 통과시킨 뒤 다음 기능을 얹는다. 모든 Phase는 독립적으로 실행·검증 가능하며, 실 Qdrant/DB 파괴 작업은 마지막 게이트 Phase에서만 수행한다.
>
> 상위 설계·근거는 [plan.md](./plan.md) 참고. 이 문서는 실행 순서와 완료기준(DoD)에 집중한다.

## 진행 개요

| Phase | 한 줄 목표 | 누적 문서 수 | 새 기능 |
|---|---|---|---|
| 0 | 스캐폴딩 + 골드 라벨 추출 | — | 자산 준비 |
| 1 | 95개 복원만으로 end-to-end 동작 | 95 | 최소 파이프라인 |
| 2 | 택소노미 상수화(드리프트 방지) | 95 | 하드닝 |
| 3 | reference react/react-dom 규칙 확장 | 125 | 순수 경로 규칙 |
| 4 | learn 레벨 + rsc/rules 확장 | 141 | 판단 규칙 |
| 5 | 소비처 경로 통일 + 통합 dry-run | 141 | 소비처 정합 |
| 6 | 실 인덱싱/시딩 (사용자 게이트) | 141 | 실 반영 |

---

## Phase 0 — 스캐폴딩 & 골드 라벨 추출

**목표:** 코드 없이 데이터 자산과 폴더 구조만 먼저 확보.

**작업**
- `app/scripts/enrichment/` 패키지 생성(`__init__.py`).
- 일회성 추출: `git show 0febce2:react_complete_learning_data.json`에서 `content` 제외 5필드(`source_path`,`title`,`main_category`,`sub_category`,`topic_group`)만 뽑아 `app/scripts/enrichment/curated_labels.json` 생성. 키 = 정규화된 `source_path`(forward-slash 소문자).

**검증 / DoD**
- `curated_labels.json` 엔트리 95개, 각 엔트리에 5필드 존재.
- `main_category` 2종·`sub_category` 6종 분포가 실측치(41/54, 1~4단계+참조2종)와 일치.

---

## Phase 1 — 최소 파이프라인 (95개 복원만)

**목표:** 규칙 없이, 복원 라벨만으로 가공본을 만들어 **소비처가 도는 것**을 최우선 확인.

**작업**
- 신규 `app/scripts/enrich_learning_data.py`:
  1. raw(`react_docs_data.json`) 로드 → `source` 정규화 → `source_path`.
  2. `curated_labels.json`에 매칭되는 문서만 채택(95개). 라벨 5필드 부여 + `content`는 raw 원문 유지.
  3. 미매칭 문서는 이 Phase에선 **건너뜀**(경고만 출력).
  4. 프로젝트 루트에 `react_complete_learning_data.json` 기록.
- title은 우선 `curated_labels.json` 값 사용(이미 존재).

**검증 / DoD**
- 산출물 95개, 전 문서 6필드 완비(필수 5개 non-empty).
- 복원 95개가 `curated_labels.json`과 정확 일치(회귀 방지 assert).
- **in-memory Qdrant** dry-run: 청킹→임베딩→업서트→검색 성공(기존 scratchpad 방식 재사용, 실 클러스터 미접촉).
- `seed.py` 필드 매핑 스모크: JSON 로드 후 `LearningContent` 매핑에 KeyError 없음(임시 SQLite 또는 롤백 트랜잭션).

---

## Phase 2 — 택소노미 상수화 (드리프트 방지)

**목표:** 문자열 정확일치 리스크를 구조적으로 제거. 동작 변화 없음(순수 리팩터).

**작업**
- 신규 `app/core/taxonomy.py`: `LEVEL_TO_SUBCATEGORIES`(현 `qdrant_service.py:29-33`), 정본 `MAIN_CATEGORIES`, `SUB_CATEGORIES` 상수 정의.
- `app/services/qdrant_service.py:29-33`을 taxonomy import로 교체.
- `enrich_learning_data.py`의 검증 로직이 taxonomy 상수를 참조하도록 연결.

**검증 / DoD**
- `qdrant_service` import·동작 불변(기존 레벨 검색 스모크 통과).
- 산출 `sub_category` 집합 ⊆ taxonomy 상수, `LEVEL_TO_SUBCATEGORIES`의 4개 레벨값이 데이터에 실재.

---

## Phase 3 — reference 규칙 확장 (순수 경로 매핑, 쉬움)

**목표:** 결정적 경로 규칙만으로 신규 reference 30개 추가(+30 → 125).

**작업**
- 신규 `app/scripts/enrichment/rules.py`에 경로 규칙:
  - `reference/react/*` → `main_category=API 레퍼런스 (Reference)`, `sub_category=React 핵심 API`.
  - `reference/react-dom/*` → `sub_category=React DOM API`.
  - (과거 패턴과 100% 일치 확인됨.)
- `enrich_learning_data.py`: 미매칭 문서 중 위 규칙에 걸리는 것 라벨 생성. title은 frontmatter 정규식 추출(`split('---',2)` 패턴 재사용).
- `topic_group`은 이 Phase에선 None 허용(nullable).

**검증 / DoD**
- 산출물 125개, 신규 30개의 `sub_category`가 규칙값과 일치.
- title 추출 성공(실패 시 경고 목록 출력).

---

## Phase 4 — learn 레벨 + 신규 reference 경로 확장 (판단 규칙) → 141 완성

**목표:** 판단이 필요한 나머지 16개(learn 7 + rsc 5 + rules 4) 추가.

**작업**
- `rules.py`에 명시 매핑 테이블 추가:
  - **learn 7개 레벨(초기 제안, 검토 확정)**:
    - `setup.md`,`creating-a-react-app.md`,`build-a-react-app-from-scratch.md`,`index.md` → `1단계: 사전 준비 ⚙️`
    - `describing-the-ui.md`,`adding-interactivity.md`,`managing-state.md` → `2단계: 메인 학습 코스 (초급) 入门`
  - **신규 reference 경로**: `reference/rsc/*`(5), `reference/rules/*`(4) → 신규 `sub_category` 값 부여(예: `React Server Components`, `React 규칙` — 확정 필요). 레벨 검색 비대상이라 값 선택은 안전.
- 규칙 미적용 문서는 라벨 비우지 말고 **경고 출력**(silent 오라벨 방지).

**검증 / DoD**
- 산출물 **141개**, blog·warnings 제외 확인.
- 모든 필수 필드 non-empty, `sub_category` ⊆ (taxonomy 6종 + rsc/rules 신규값).
- learn 7개 레벨·rsc/rules 신규값이 사용자 검토로 확정됨.

---

## Phase 5 — 소비처 경로 통일 + 통합 dry-run

**목표:** 두 소비처가 같은 파일을 보게 하고, 전체 흐름을 실 반영 없이 검증.

**작업**
- `app/scripts/seed.py:15-17` `DATA_FILE_PATH`를 프로젝트 루트 기준으로 정정(`..`×3 → ×2). `index_data.py`도 동일 경로 상수 사용하도록 정렬(선택).

**검증 / DoD**
- `index_data.py` 전량(141개) in-memory Qdrant 인덱싱·검색 성공, 레벨 필터(`초급/중급/고급`)가 실제로 문서 반환.
- `seed.py`가 141개를 임시/롤백 DB에 매핑 성공(KeyError 없음, source_path 유니크).

---

## Phase 6 — 실 인덱싱/시딩 (사용자 게이트, 파괴적)

**목표:** 실 Qdrant 컬렉션·PostgreSQL에 반영. **파괴적 작업이라 사용자 확인 필수.**

**작업 (사용자 승인 후)**
- `.env` 준비 확인 → `uv run python index_data.py`(주의: `recreate_collection`으로 기존 컬렉션 삭제 후 재생성).
- `uv run python -m app.scripts.seed`(PostgreSQL 시딩).

**검증 / DoD**
- Qdrant 컬렉션 포인트 수 = 청크 수(예상치와 일치).
- `get_contexts_by_level` 각 레벨이 비어있지 않은 결과 반환.
- `learning_content` 테이블 행 수 = 141.

---

## 커밋 전략(권장)

각 Phase를 개별 커밋으로 분리(예: `feat: enrichment Phase 1 - 95개 복원 파이프라인`). 커밋은 사용자가 수동 수행.

## 열린 결정 사항 (Phase 4에서 확정)
- 신규 learn 7개의 레벨 배정(위 초기 제안 검토).
- `reference/rsc`·`reference/rules` 9개의 `sub_category` 명칭.
