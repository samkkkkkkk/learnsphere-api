# 가공 파이프라인 재구축 — 구현 체크리스트 (tasks)

> [detail_plan.md](./detail_plan.md)를 실행 단위 태스크로 분해한 체크리스트. 각 Phase는 순서대로 진행하고, **DoD 항목이 모두 체크되면** 다음 Phase로 넘어간다. `[ ]`를 `[x]`로 바꿔 진행 상태를 기록한다.
>
> 상위 설계·근거: [plan.md](./plan.md)
>
> **테스트 원칙:** 검증은 일회성 스크립트가 아니라 `tests/test_enrichment.py`(pytest)에 **재현 가능한** 형태로 남긴다(파이프라인은 React 문서 갱신 시 재실행되므로). 원래 이 앱을 망가뜨린 실패 유형(빈 `sub_category`·문자열 불일치·빈 `title`)을 직접 겨냥하는 회귀 테스트를 우선한다.

## 전체 진행 현황

- [x] **Phase 0** — 스캐폴딩 & 골드 라벨 추출
- [x] **Phase 1** — 최소 파이프라인 (95개 복원)
- [x] **Phase 2** — 택소노미 상수화
- [x] **Phase 3** — reference 규칙 확장 (→125)
- [x] **Phase 4** — learn/rsc/rules 확장 (→141)
- [x] **Phase 5** — 소비처 경로 통일 + 통합 dry-run
- [x] **Phase 6** — 실 인덱싱/시딩 (2026-07-24 사용자 승인 후 실행 완료)

> **상태(2026-07-23):** Phase 0–5 구현 완료, 산출물 141개 생성, pytest 26개 전부 통과. Phase 6(실 Qdrant `recreate_collection` + DB 시딩)은 파괴적이라 사용자 승인 후 실행.
>
> **점검(2026-07-24):** Phase 0–5 전 체크리스트 항목을 실측 재검증 후 체크 완료 — 산출물 수치(95/125→141)·분포·라벨 정확 일치·pytest 26개 통과 재확인, `index_data.py` 전량(571 청크) in-memory dry-run 및 `seed.py` 임시 SQLite 매핑 스모크(141/141) 직접 실행으로 통과.

---

## Phase 0 — 스캐폴딩 & 골드 라벨 추출

### 구현
- [x] `app/scripts/enrichment/` 디렉토리 생성
- [x] `app/scripts/enrichment/__init__.py` 생성 (빈 파일)
- [x] 추출 스크립트 작성/실행: `git show 0febce2:react_complete_learning_data.json` 파싱 (`extract_curated_labels.py`)
- [x] `content` 필드 제외, 5필드(`source_path`,`title`,`main_category`,`sub_category`,`topic_group`)만 추출
- [x] `source_path`를 정규화(백슬래시→`/`, 소문자)하여 dict 키로 사용
- [x] `app/scripts/enrichment/curated_labels.json` 저장 (UTF-8, `ensure_ascii=False`)

### 검증 (DoD)
- [x] `curated_labels.json` 엔트리 수 == 95
- [x] 각 엔트리에 5필드 모두 존재
- [x] `main_category` 분포: `학습 과정 (Learn)`==41, `API 레퍼런스 (Reference)`==54
- [x] `sub_category` 6종 분포가 실측치와 일치 (1단계5·2단계10·3단계14·4단계12·React핵심API36·ReactDOM API18)

---

## Phase 1 — 최소 파이프라인 (95개 복원만)

### 구현
- [x] `app/scripts/enrich_learning_data.py` 생성 (`python -m app.scripts.enrich_learning_data` 실행 가능)
- [x] raw `react_docs_data.json` 로드 (165개)
- [x] 각 문서 `source` → 정규화 → `source_path` 생성
- [x] `curated_labels.json` 매칭 문서만 채택 (95개), 라벨 5필드 부여
- [x] `content`는 raw 원문 그대로 유지
- [x] 미매칭 문서는 건너뛰되 경고 출력 (`[SKIP] <source_path>`) — *Phase 4에서 하드 실패(ValueError)로 강화됨 (silent 오라벨 방지)*
- [x] 프로젝트 루트에 `react_complete_learning_data.json` 기록 (UTF-8, `ensure_ascii=False`)

### 검증 (DoD)
- [x] 산출물 문서 수 == 95 — *Phase 1 시점 기준; 현재 141 (curated 95 + 규칙 46, `test_curated_and_rule_split`로 검증)*
- [x] 전 문서 6필드 존재, 필수 5개(`content`,`title`,`main_category`,`sub_category`,`source_path`) non-empty
- [x] 복원 95개 라벨이 `curated_labels.json`과 정확 일치 (assert 통과, `test_curated_labels_recovered`)
- [x] in-memory Qdrant dry-run: 청킹→임베딩→업서트→검색 성공 (실 클러스터 미접촉, `test_search_relevance`)
- [x] `seed.py` 매핑 스모크: JSON 로드 후 `LearningContent` 매핑 KeyError 없음 (임시 SQLite/롤백)

---

## Phase 2 — 택소노미 상수화 (드리프트 방지)

### 구현
- [x] `app/core/taxonomy.py` 생성
- [x] `LEVEL_TO_SUBCATEGORIES` 정의 (현 `qdrant_service.py:29-33` 내용 이전)
- [x] `MAIN_CATEGORIES`, `SUB_CATEGORIES` 정본 상수 정의
- [x] `app/services/qdrant_service.py:29-33` 하드코딩을 taxonomy import로 교체
- [x] `enrich_learning_data.py` 검증 로직이 taxonomy 상수 참조하도록 연결 (`validate()`)

### 검증 (DoD)
- [x] `qdrant_service` import 정상, 레벨 검색 스모크 동작 불변 (`test_taxonomy_matches_qdrant_service_source` + in-memory 레벨 필터 dry-run)
- [x] 산출 `sub_category` 집합 ⊆ `SUB_CATEGORIES`
- [x] `LEVEL_TO_SUBCATEGORIES`의 4개 레벨값이 모두 데이터에 실재 (1단계9·2단계13·3단계14·4단계12)

---

## Phase 3 — reference 규칙 확장 (순수 경로 매핑)

### 구현
- [x] `app/scripts/enrichment/rules.py` 생성
- [x] 규칙: `reference/react/*` → `main_category=API 레퍼런스 (Reference)`, `sub_category=React 핵심 API`
- [x] 규칙: `reference/react-dom/*` → `sub_category=React DOM API`
- [x] `enrich_learning_data.py`: 미매칭 문서 중 규칙 적용 대상 라벨 생성
- [x] title은 frontmatter 정규식 추출 (`split('---',2)` 패턴 재사용)
- [x] `topic_group`은 None 허용

### 검증 (DoD)
- [x] 산출물 문서 수 == 125 — *Phase 3 시점 기준; 현재 141*
- [x] 신규 30개의 `sub_category`가 규칙값과 일치 (react 13 → React 핵심 API, react-dom 17 → React DOM API)
- [x] title 추출 성공, 실패 문서는 경고 목록 출력 — *경고 대신 파일명 stem fallback으로 처리 (react-dom 4개, `test_title_fallback_for_frontmatterless_docs`)*

---

## Phase 4 — learn 레벨 + rsc/rules 확장 (판단 규칙) → 141

### 선행 결정 (구현 전 확정)
- [x] 신규 learn 7개 레벨 배정 확정 (초기 제안대로 확정)
- [x] `reference/rsc`(5)·`reference/rules`(4) `sub_category` 명칭 확정 (`React Server Components`, `React 규칙`)

### 구현
- [x] `rules.py`에 learn 레벨 명시 매핑 추가:
  - [x] `setup.md`,`creating-a-react-app.md`,`build-a-react-app-from-scratch.md`,`index.md` → `1단계: 사전 준비 ⚙️`
  - [x] `describing-the-ui.md`,`adding-interactivity.md`,`managing-state.md` → `2단계: 메인 학습 코스 (초급) 入门`
- [x] `rules.py`에 신규 reference 경로 매핑 추가:
  - [x] `reference/rsc/*` → `React Server Components`
  - [x] `reference/rules/*` → `React 규칙`
- [x] 규칙 미적용 문서는 라벨 비우지 말고 경고 출력 (silent 오라벨 방지) — *경고보다 강한 하드 실패(ValueError)로 구현 (`test_build_enriched_hard_fails_on_unlabeled`)*

### 검증 (DoD)
- [x] 산출물 문서 수 == 141
- [x] blog(18)·warnings(6) 제외 확인 (포함되지 않음)
- [x] 모든 필수 필드 non-empty
- [x] `sub_category` ⊆ (taxonomy 6종 + rsc/rules 신규값)
- [x] 규칙 미적용(경고) 문서 0건

---

## Phase 5 — 소비처 경로 통일 + 통합 dry-run

### 구현
- [x] `app/scripts/seed.py:15-17` `DATA_FILE_PATH`를 프로젝트 루트 기준으로 정정 (`..`×3 → ×2)
- [x] `index_data.py` 경로도 동일 기준으로 정렬 (선택, 공통 상수화) — *루트 기준 상대경로로 정합 확인 (공통 상수화는 미적용, 선택 사항)*

### 검증 (DoD)
- [x] `index_data.py` 전량(141개) in-memory Qdrant 인덱싱·검색 성공 (571 청크 업서트·검색 확인, 2026-07-24 dry-run)
- [x] 레벨 필터 `초급`/`중급`/`고급` 각각 비어있지 않은 문서 반환
- [x] `seed.py`가 141개를 임시/롤백 DB에 매핑 성공 (KeyError 없음)
- [x] `source_path` 유니크 제약 위반 없음 (distinct 141/141)

---

## Phase 6 — 실 인덱싱/시딩 (사용자 게이트, 파괴적)

> ⚠️ 파괴적 작업. `index_data.py`의 `recreate_collection`은 기존 Qdrant 컬렉션을 삭제 후 재생성한다. **반드시 사용자 승인 후 실행.**

### 선행 조건
- [x] `.env` 준비 확인 (`QDRANT_URL`,`QDRANT_API_KEY`,`DATABASE_URL` 등)
- [x] PostgreSQL 컨테이너 기동 (`docker compose up -d`, healthy 확인)
- [x] 기존 Qdrant 컬렉션 덮어쓰기 사용자 최종 승인 (2026-07-24)

### 실행
- [x] `uv run python index_data.py` (Qdrant 인덱싱, 571 포인트 업로드)
- [x] `uv run python -m app.scripts.seed` (PostgreSQL 시딩, 141개 추가)

### 검증 (DoD)
- [x] Qdrant 컬렉션 포인트 수 == 청크 수 (571 == 571)
- [x] `get_contexts_by_level` 각 레벨(초급/중급/고급) 비어있지 않은 결과 반환 (22/14/12 토픽)
- [x] `learning_content` 테이블 행 수 == 141 (distinct `source_path` 141)

> **후속 수정(2026-07-24):** 실 클러스터 검증 중 `sub_category` 필터가 400(Bad Request)으로 실패 — Qdrant Cloud는 payload 필터에 keyword 인덱스가 필수(in-memory dry-run에서는 미노출). `index_data.py`에 `create_payload_index(sub_category, KEYWORD)` 추가 + 라이브 컬렉션에 인덱스 생성 후 재검증 통과.

---

## 부록: 열린 결정 사항 (Phase 4 선행)

**신규 learn 7개 레벨 — 초기 제안**
| source_path (파일명) | title | 제안 레벨 |
|---|---|---|
| `setup.md` | 설정하기 | 1단계: 사전 준비 ⚙️ |
| `creating-a-react-app.md` | 새로운 React 앱 만들기 | 1단계: 사전 준비 ⚙️ |
| `build-a-react-app-from-scratch.md` | 처음부터 React 앱 만들기 | 1단계: 사전 준비 ⚙️ |
| `index.md` | 빠르게 시작하기 | 1단계: 사전 준비 ⚙️ |
| `describing-the-ui.md` | UI 표현하기 | 2단계: 메인 학습 코스 (초급) 入门 |
| `adding-interactivity.md` | 상호작용 추가하기 | 2단계: 메인 학습 코스 (초급) 入门 |
| `managing-state.md` | State 관리하기 | 2단계: 메인 학습 코스 (초급) 入门 |

**신규 reference 경로 sub_category — 제안값(확정 필요)**
| 경로 | 문서 수 | 제안 sub_category |
|---|---|---|
| `reference/rsc/*` | 5 | React Server Components |
| `reference/rules/*` | 4 | React 규칙 |

## 커밋 전략
- [ ] 각 Phase를 개별 커밋으로 분리 (예: `feat: enrichment Phase 1 - 95개 복원 파이프라인`)
- [ ] 커밋은 사용자가 수동 수행
