# 가공(Enrichment) 파이프라인 배치 방식 비교

> React 문서 데이터의 가공 단계를 재구축할 때, 이 파이프라인을 **이 프로젝트에 포함**할지 **별도로 분리**할지에 대한 트레이드오프 분석과 결정 기록.

## 배경

가공 단계는 **드물게 실행되는 배치 단계**다(React 문서가 갱신되거나 커리큘럼 레벨을 다시 매길 때만 실행). API 요청 처리 런타임에는 전혀 관여하지 않는다.

```
[1] React 공식 GitHub 클론 → .md 추출
        ↓  산출물: react_docs_data.json   (source + content 만)   ✅ 저장소에 있음
[2] 가공(enrichment) 단계  ← ★ 재구축 대상 (유실됨)
        ↓  산출물: react_complete_learning_data.json
           (+ main_category, sub_category=학습레벨, title, source_path)
[3] index_data.py  → 벡터화 → Qdrant       (가공 산출물을 읽음)
[4] seed.py        → PostgreSQL 시딩        (역시 같은 파일을 읽음)
```

- **입력**: `react_docs_data.json` (165개 문서, `source` + `content`)
- **출력**: `react_complete_learning_data.json` (`main_category`, `sub_category`, `title`, `source_path` 추가)
- **소비처**: `index_data.py`(Qdrant 벡터화), `seed.py`(PostgreSQL 시딩)

---

## 근거 1: 데이터 계약(레벨 택소노미) 결합도 — 가장 중요

가공 단계가 찍는 `sub_category` 값은 `qdrant_service.py`의 레벨 매핑(`"1단계: 사전 준비 ⚙️"`, `"3단계: 메인 학습 코스 (중급) 🚀"` 등)과 **문자 하나까지 정확히** 일치해야 한다. 안 그러면 검색 필터가 아무것도 못 잡는다.

- **In-project**: 레벨 문자열을 공용 상수 모듈(예: `app/core/taxonomy.py`)로 두고 가공 스크립트와 `qdrant_service.py`가 함께 import → 드리프트가 구조적으로 불가능.
- **Separate**: 두 저장소가 같은 문자열을 각자 하드코딩 → 한쪽만 바뀌면 조용히 깨짐. 막으려면 버전이 붙은 스키마/계약을 별도로 관리해야 하는데 지금 규모엔 과하다.

→ **In-project 우세.** 결합이 강한 만큼 한 곳에 두는 게 안전하다.

## 근거 2: 의존성·배포 풋프린트

- **In-project**: 가공에 필요한 추가 의존성(frontmatter 파서, LLM 라벨링 시 `openai` — 이미 있음)이 API의 `pyproject.toml`에 섞인다. 다만 이 프로젝트는 이미 `index_data.py` 때문에 torch/transformers를 지고 있어서, 배포 이미지가 무거운 건 **이미 발생한 문제**다.
- **Separate**: API 런타임을 깔끔하게 유지. 단, 근본적으로 슬림하게 하려면 `index_data.py`까지 같이 분리해야 의미가 있다.

→ 순수 배포 슬림함만 보면 **Separate 우세**, 하지만 이 프로젝트에선 이미 무거워서 **효과가 반감**된다.

## 근거 3: 실행 생애주기(lifecycle)

가공은 "가끔 한 번" 도는 배치이고 API는 상주 서비스다. 생애주기가 다른 것을 한 배포 단위에 묶는 건 원칙적으로 냄새다.

- **Separate**가 이 원칙엔 부합.
- 그러나 이 저장소엔 이미 `app/scripts/seed.py`, `migrate_backup_to_datefolders.py`처럼 **드물게 도는 배치 스크립트가 관례적으로 들어와 있다.** 즉 "one-off 스크립트는 `app/scripts/`에 둔다"는 컨벤션이 이미 있어 In-project가 이질적이지 않다.

→ 원칙은 Separate, **기존 관례는 In-project**. 팽팽하다.

## 근거 4: 운영·온보딩 단순성

- **In-project**: `git clone` 한 번, `uv sync` 한 번, `uv run python -m app.scripts.enrich`로 끝. 전체 흐름(추출본 → 가공 → 인덱싱 → 시딩)이 한 저장소에서 눈에 보인다. 솔로/소규모에 최적.
- **Separate**: 저장소·환경 2개, "어느 버전 산출물이 어느 API와 맞나"를 사람이 관리. 오버헤드가 실질적이다.

→ **In-project 우세** (현재 규모 기준).

## 근거 5: 재사용성·소유권

- **Separate**가 유리한 유일하게 강한 시나리오: 이 "React 문서 → 커리큘럼 라벨링"을 **다른 프로젝트에서도 재사용**하거나, **콘텐츠팀 등 다른 주체가 소유**하게 될 때. 그때는 독립 패키지가 맞다.
- 지금은 레벨 택소노미가 **이 앱 전용**이라 재사용 여지가 낮다.

→ 미래에 재사용/분리 소유가 예상되면 Separate, 아니면 In-project.

---

## 요약

| 근거 | In-project | Separate |
|---|---|---|
| 1. 레벨 택소노미 결합도 | ✅ 상수 공유로 드리프트 방지 | ⚠️ 계약 관리 필요 |
| 2. 배포 풋프린트 | ⚠️ (단 이미 무거움) | ✅ 슬림 |
| 3. 실행 생애주기 | 관례상 OK | ✅ 원칙 부합 |
| 4. 운영·온보딩 | ✅ 단일 저장소 | ⚠️ 2배 관리 |
| 5. 재사용·소유권 | 전용이면 OK | ✅ 재사용 시 |

---

## 결정: In-project (단, 분리 가능한 형태로)

지금 이 프로젝트는 **솔로/초기 단계 + 레벨 택소노미가 앱에 강결합 + `app/scripts/` 배치 관례 존재**라, 근거 1·3·4가 모두 In-project를 가리킨다. 따라서:

- 가공 스크립트를 `app/scripts/enrich_learning_data.py`로 넣는다.
- 레벨 문자열은 `app/core/taxonomy.py` 상수로 빼서 `qdrant_service.py`와 공유한다.

배포 슬림함·미래 분리(근거 2·5)를 절충하기 위해 **uv의 dependency group**을 활용한다:

- 가공 전용 추가 의존성을 `[dependency-groups] enrich = [...]`로 격리.
- 배포 시 `uv sync --no-group enrich`로 API 런타임에서 제외.

즉 코드는 한 저장소에 두되 런타임 의존성은 분리 — In-project의 결합 이점과 Separate의 슬림 이점을 동시에 취한다. 나중에 재사용 필요가 생기면 `app/scripts/enrich_*` + `taxonomy.py`만 떼어내 패키지화하면 되므로 지금 선택이 미래를 막지 않는다.

## 미해결 결정 사항

가공 로직의 핵심인 **레벨(초급/중급/고급) 라벨링 기준**을 정해야 한다:

- **A. source 경로 규칙 기반 수동 매핑 테이블** — 결정적·재현 가능, 문서 추가 시 수동 갱신 필요.
- **B. LLM 자동 분류** — 신규 문서 자동 대응, 비결정적·검수 필요(`openai` 의존성 이미 존재).
