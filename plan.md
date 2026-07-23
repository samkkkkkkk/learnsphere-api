# 가공(Enrichment) 파이프라인 재구축 — In-project 방식

## Context

React 학습 앱의 데이터 파이프라인은 `raw 추출본 → 가공 → 벡터화(Qdrant)/시딩(PostgreSQL)` 구조다. 이 중 **가공 단계**(raw에 `main_category`/`sub_category`(학습레벨)/`title`/`source_path`/`topic_group`를 부여해 `react_complete_learning_data.json`을 생성)의 스크립트와 산출물이 유실됐다. 소비처(`index_data.py`, `seed.py`)는 이 파일을 읽기만 하고 생성하는 코드가 저장소에 없어, 현재 인덱싱·시딩이 불가능하다.

조사 결과 두 가지가 밝혀졌다:
1. **과거 가공본이 git 커밋 `0febce2`에 온전히 존재**(95개 문서, 2.7MB, 6개 필드 완비). 현재 raw(`react_docs_data.json`, 165개)와 **경로 정규화 후 95/95 완전 매칭** → 사람이 큐레이션한 라벨을 재작업 없이 복원 가능.
2. 신규 라벨이 필요한 문서는 70개(reference 39, blog 18, learn 7, warnings 6)뿐.

**결정(사용자 확정):** 커버리지 = **복원 95 + 신규 learn 7·reference 39 라벨링**(blog·warnings 제외 → 최종 **141개**). 신규 라벨링 방식 = **규칙 기반 수동 매핑**. 배치 스크립트는 **In-project**(`app/scripts/`)에 두고, 레벨 택소노미는 공용 상수로 분리해 `qdrant_service.py`와 공유(드리프트 방지).

목표: 가공 파이프라인을 저장소 내에 복원해 `uv run python -m app.scripts.enrich_learning_data`로 141개 문서의 가공본을 재생성하고, 이후 `index_data.py`/`seed.py`가 정상 소비하도록 만든다.

## 산출물 스키마 (소비처 요구 — 확정)

`react_complete_learning_data.json`의 각 문서 객체:

| 필드 | 필수성 | 소비처 | 비고 |
|---|---|---|---|
| `content` | 필수 | index_data.py(대괄호) | raw 원문 그대로(청킹·임베딩용). seed.py는 안 읽음 |
| `title` | 필수 | seed.py(대괄호), index_data.py | frontmatter에서 추출 |
| `main_category` | 필수 | seed.py(대괄호), index_data.py | 경로 기반 |
| `sub_category` | 필수 | seed.py(대괄호), index_data.py | 학습레벨/참조카테고리. **문자 정확일치 필수** |
| `source_path` | 필수 | 둘 다(대괄호) | DB UNIQUE 키 & dedup 키. forward-slash 소문자 정규화 |
| `topic_group` | 선택 | seed.py(`.get`) | nullable, 없으면 None |

> 누락 시: `seed.py`는 KeyError로 시딩 실패(대괄호 접근). `index_data.py`는 `.get(..,'')`라 안 죽지만 메타데이터가 비어 레벨 필터 무력화.

## 정본 택소노미 (git 0febce2 실측)

- `main_category`: `학습 과정 (Learn)`(41), `API 레퍼런스 (Reference)`(54)
- `sub_category`(레벨): `1단계: 사전 준비 ⚙️`, `2단계: 메인 학습 코스 (초급) 入门`, `3단계: 메인 학습 코스 (중급) 🚀`, `4단계: 심화 탐구 🧠`, `React 핵심 API`, `React DOM API`
  - 앞 4개(1~4단계)만 `qdrant_service.py`의 `level_mapping`(초급/중급/고급)으로 검색 가능. `React 핵심 API`/`React DOM API`는 저장은 되나 레벨 검색 대상 아님(기존 동작 유지).
- `topic_group`: `Hooks (핵심 기능) 🎣`, `컴포넌트 & 엘리먼트 🧱` 등 11종(참조 문서에만, learn은 None).

## 구현 단계

### 1. 공용 택소노미 상수 분리 (근거 1: 드리프트 방지)
- 신규 `app/core/taxonomy.py`: `level_mapping`(현 `qdrant_service.py:29-33`)을 `LEVEL_TO_SUBCATEGORIES` 상수로 이동. 모든 정본 `sub_category`/`main_category` 문자열을 여기 한 곳에 정의.
- `app/services/qdrant_service.py:29-33`을 상수 import로 교체(하드코딩 제거). 동작 동일, 문자열 출처 단일화.

### 2. 복원 라벨 자산 추출 (95개 골드 라벨)
- 일회성: `git show 0febce2:react_complete_learning_data.json`에서 `content`를 제외한 라벨 5필드만 뽑아 `app/scripts/enrichment/curated_labels.json`으로 저장(경량, ~95엔트리). 키 = 정규화 `source_path`.
- 이 자산을 커밋 → 이후 가공은 git 이력 없이도 재현 가능.

### 3. 규칙 테이블 정의
- 신규 `app/scripts/enrichment/rules.py`:
  - **main_category(경로 기반)**: `learn/*` → `학습 과정 (Learn)`, `reference/*` → `API 레퍼런스 (Reference)`.
  - **신규 learn 7개 레벨(명시 매핑)** — 챕터 개요 페이지. 제안 초기값(검토 대상):
    - `setup.md`, `creating-a-react-app.md`, `build-a-react-app-from-scratch.md`, `index.md` → `1단계: 사전 준비 ⚙️`
    - `describing-the-ui.md`, `adding-interactivity.md`, `managing-state.md` → `2단계: 메인 학습 코스 (초급) 入门`
  - **신규 reference sub_category(경로 기반)**: `reference/react/*` → `React 핵심 API`, `reference/react-dom/*` → `React DOM API`(과거 패턴과 100% 일치). 신규 경로 `reference/rsc/*`(5), `reference/rules/*`(4)는 과거본에 없음 → 신규 `sub_category` 라벨 부여(예: `React Server Components`, `React 규칙`; 값 확정 필요, 레벨검색 비대상이라 안전).
  - **topic_group**: 규칙으로 도출 가능한 것만 부여, 나머지 None(nullable 허용).
  - 어떤 규칙에도 안 걸리는 문서는 **라벨 비우지 말고 경고 출력**(silent 오라벨 방지).

### 4. 가공 엔트리포인트
- 신규 `app/scripts/enrich_learning_data.py` (`python -m app.scripts.enrich_learning_data`):
  1. raw 165개 로드 → blog/warnings 제외(learn+reference만) → 141개.
  2. `source` 정규화(백슬래시→`/`, 소문자) = `source_path`.
  3. `curated_labels.json`에 있으면 골드 라벨 적용(95개), 없으면 `rules.py`로 라벨 생성(46개).
  4. `title`은 content frontmatter에서 정규식 추출(stdlib, PyYAML 불필요 — `index_data.py`의 `split('---',2)` 패턴 재사용).
  5. `content`는 raw 원문 유지.
  6. 검증(아래) 통과 시 프로젝트 루트에 `react_complete_learning_data.json` 기록.

### 5. 소비처 경로 불일치 수정
- 현재 `seed.py:15-17`은 프로젝트 **부모**(`C:\WorkSpace\...`)를, `index_data.py:26`은 **cwd**를 가리킴 → 서로 다름.
- 둘 다 **프로젝트 루트** 기준으로 통일(`seed.py`의 `..` 3개 → 2개로 수정, 또는 공통 경로 상수화).

### 6. 의존성
- 규칙 기반 + stdlib(정규식 frontmatter 파싱)라 **신규 의존성 없음**. `pyproject.toml` 변경 불필요. (LLM/무거운 파서 미사용 → dependency-group 분리도 현시점 불필요, 향후 확장 시 재고.)

## 파일 변경 요약

| 파일 | 종류 | 내용 |
|---|---|---|
| `app/core/taxonomy.py` | 신규 | 정본 택소노미 상수(레벨 매핑 포함) |
| `app/services/qdrant_service.py` | 수정 | `level_mapping`을 taxonomy import로 교체 |
| `app/scripts/enrichment/curated_labels.json` | 신규(자산) | git 0febce2에서 추출한 95개 골드 라벨 |
| `app/scripts/enrichment/rules.py` | 신규 | 신규 문서 규칙 매핑 테이블 |
| `app/scripts/enrich_learning_data.py` | 신규 | 가공 엔트리포인트 |
| `app/scripts/seed.py` | 수정 | `DATA_FILE_PATH` 경로 정정 |
| `index_data.py` | (선택) | 경로 상수 통일 시 |

## 검증 (end-to-end)

1. **가공 실행**: `uv run python -m app.scripts.enrich_learning_data` → 출력 141개 확인.
2. **스키마 검증**(스크립트 내 assert):
   - 전 문서에 6필드 존재(`topic_group` 제외 필수 5개 non-empty).
   - `main_category` ∈ 정본 2값, `sub_category` ∈ 정본 6값(+rsc/rules 신규값), `source_path` 유니크·정규화.
   - 복원 95개가 `curated_labels.json`과 정확히 일치(회귀 방지).
3. **택소노미 드리프트 검사**: 산출 `sub_category` 집합이 `taxonomy.py` 상수의 상위집합인지, `level_mapping` 4값이 모두 데이터에 실재하는지 확인.
4. **소비처 dry-run**:
   - `index_data.py` 청킹·임베딩·업서트를 **in-memory Qdrant**로 검증(기존 scratchpad 검증 방식 재사용 — 실 클러스터 안 건드림).
   - `seed.py`의 JSON 로드+필드 매핑을 임시 SQLite/트랜잭션 롤백으로 스모크 테스트(실 DB 시딩은 사용자 확인 후).
5. **실 인덱싱/시딩은 게이트**: `index_data.py`는 `recreate_collection`으로 기존 컬렉션을 파괴 후 재생성하므로, 실 Qdrant/PostgreSQL 반영은 사용자 확인 뒤 별도 실행.

## 범위 밖 / 알려진 한계

- blog(18)·warnings(6)는 이번 가공 대상 제외(레벨 커리큘럼 부적합).
- `React 핵심 API`/`React DOM API`/rsc/rules 참조 문서는 저장되지만 `get_contexts_by_level` 검색 대상 아님(기존 동작 유지, 이번 변경 아님).
- 긴 청크(임베딩 512토큰 초과) 재분할 개선은 별도 과제(이번 범위 밖).
- 신규 learn 7개 레벨 지정·rsc/rules 신규 sub_category 값은 초기 제안값 → 구현 중 사용자 검토로 확정.
