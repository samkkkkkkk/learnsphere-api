# Swagger 테스트 가이드

FastAPI가 자동 생성하는 Swagger UI(`/docs`)로 LearnSphere API를 수동 테스트하는 방법을 정리한다. 각 시나리오는 **호출 방법 → 기대 결과 → 확인 포인트** 순으로 기술한다.

> (2026-07-24) 레슨 저장소가 파일에서 PostgreSQL(세대/버전)로 이관되어 Lesson/Admin 엔드포인트가 교체됐다. 과거 실측 기록 [swagger_test_results.md](./swagger_test_results.md)는 이관 **이전** API 기준이다.
>
> 관련 문서: [DB_MIGRATION_PLAN.md](./DB_MIGRATION_PLAN.md) · [plan.md](./plan.md) · [tasks.md](./tasks.md)

## 1. 사전 준비

| 항목 | 명령/확인 |
|---|---|
| PostgreSQL 기동 | `docker compose up -d` → `docker compose ps`에서 `learnsphere-postgres`가 `healthy` |
| `.env` 확인 | `DATABASE_URL`, `QDRANT_URL`, `QDRANT_API_KEY`, `OPENAI_API_KEY`, `ADMIN_API_KEY` 설정 |
| DB 마이그레이션 | `uv run alembic upgrade head` (기존 create_all DB는 최초 1회 `alembic stamp 0001` 후) |
| 데이터 준비 | Qdrant 인덱싱(571 포인트)·DB 시딩(141행) 완료 상태 — 미완이면 `uv run python index_data.py`, `uv run python -m app.scripts.seed` |
| 서버 실행 | `uv run uvicorn app.main:app --port 8000` |
| Swagger UI 접속 | http://127.0.0.1:8000/docs (ReDoc: http://127.0.0.1:8000/redoc) |

### 인증 방법 (Admin / Webhooks 태그)

관리자 엔드포인트는 `X-Admin-API-Key` 헤더가 `.env`의 `ADMIN_API_KEY` 값과 일치해야 한다.
Swagger 우측 상단 **Authorize 버튼은 없고**, 각 엔드포인트를 펼쳐 **Try it out**을 누르면 나타나는 `x-admin-api-key` 파라미터 입력란에 키 값을 **요청마다 직접 입력**한다.

인증 실패 케이스도 테스트 대상이다:

- 키 미입력 또는 오입력 → `401 {"detail": "유효하지 않은 관리자 API 키입니다."}`
- 서버에 `ADMIN_API_KEY` 미설정 → `503`

---

## 2. 기본 상태 확인 (인증 불필요)

### 2-1. `GET /` — 루트

- **방법**: Try it out → Execute
- **기대**: `200` `{"message": "Welcome to the Learning Platform API!"}`

### 2-2. `GET /api/health` — 헬스 체크

- **방법**: Try it out → Execute
- **기대**: `200` `{"status": "ok"}`

---

## 3. 시딩 데이터 검증 (인증 불필요)

### 3-1. `GET /api/v1/contents/{subject_name}` — 주제별 콘텐츠 목록

- **방법**: `subject_name`에 `React` 입력 → Execute
- **기대**: `200`, 배열 길이 **141**
- **확인 포인트**:
  - 각 항목에 `title`, `main_category`, `sub_category`, `topic_group` 존재
  - `main_category`는 `학습 과정 (Learn)` / `API 레퍼런스 (Reference)` 2종
  - `sub_category`는 8종 (1~4단계 레벨 4종 + React 핵심 API·React DOM API·React Server Components·React 규칙)
- **음성 케이스**: `subject_name`에 `Vue` 등 없는 값 → `200` 빈 배열 `[]`

---

## 4. 콘텐츠 생성 (Admin, ⚠️ OpenAI 비용 발생)

### 4-1. `POST /api/v1/admin/generate-all-content` — 전체 레슨 생성

> ⚠️ gpt-4o-mini 48회 호출(초급22·중급14·고급12), 입력 약 42만 토큰 + 출력 약 6~12만 토큰 ≈ **$0.10~0.14**. 생성 결과는 새 세대(generation)의 버전으로 적재되며, 완료 시점에 원자적으로 활성 전환된다 (진행 중에는 이전 세대가 계속 서빙).

- **방법**: `x-admin-api-key` 입력 → Execute
- **기대**: 즉시 `200` `{"message": "...", "generation_id": <id>}`
- **확인 포인트**:
  - 응답은 즉시 오고 실제 생성은 백그라운드 진행 — **uvicorn 서버 로그**에서 `[Processing i/22] ... 레슨 생성 중` 진행 상황 확인
  - 6-1로 세대 status가 `running` → `completed`로 바뀌는지, 실패 토픽은 6-2의 `failed_topics`로 확인
  - 소요 시간: 호출당 수십 초 × 48회 → 수십 분 수준
- **음성 케이스**: 이미 running 세대가 있는 상태에서 재호출 → `409`

### 4-2. `POST /api/v1/webhooks/content-updated` — 웹훅 (Webhooks 태그)

4-1과 동일한 파이프라인을 트리거하는 별칭 엔드포인트. 같은 방법·같은 비용 주의.

---

## 5. 생성된 레슨 조회 (Lesson 태그, 인증 불필요)

> 레슨이 하나도 없으면(최초 상태) 5-1은 빈 객체, 5-2는 404가 정상이다.

### 5-1. `GET /api/v1/lessons` — 레벨별 레슨 목록

- **방법**: Try it out → Execute
- **기대**: `200`, `{"초급": [{id, title, number}, ...], "중급": [...], "고급": [...]}` (레슨 없으면 `{}`)

### 5-2. `GET /api/v1/lessons/{lesson_id}` — 개별 레슨

- **방법**: 5-1 응답에서 `id` 하나를 복사해 입력 → Execute
- **기대**: `200`, 스키마 `{id, level, title, core_concepts, code_examples[], quizzes[], version_id, updated_at}`
- **음성 케이스**: 존재하지 않거나 archived된 id → `404`

---

## 6. 세대/버전 관리 (Admin)

> 버전은 레슨 **재생성(또는 재이관) 시** 쌓이므로, 세대가 2개 이상일 때 복원·전환을 테스트할 수 있다.

### 6-1. `GET /api/v1/admin/generations` — 세대 목록

- **방법**: `x-admin-api-key` 입력 → Execute
- **기대**: `200`, `[{id, source(pipeline|import), status, started_at, completed_at, total_topics, succeeded, failed_count}, ...]` (최신순)

### 6-2. `GET /api/v1/admin/generations/{id}` — 세대 상세

- **방법**: 6-1의 `id` 입력 + `x-admin-api-key` → Execute
- **기대**: `200`, 목록 필드 + `failed_topics: [{level, topic, error}]`
- **음성 케이스**: 없는 id → `404`

### 6-3. `GET /api/v1/admin/lessons/{lesson_id}/versions` — 레슨 버전 목록

- **방법**: 5-1의 레슨 `id` 입력 + `x-admin-api-key` → Execute
- **기대**: `200`, `[{version_id, generation_id, title, created_at, is_current, source}, ...]` (최신순, 활성 버전에 `is_current: true`)
- **음성 케이스**: 버전 없는 레슨 id → `404`

### 6-4. `POST /api/v1/admin/lessons/{lesson_id}/restore` — 버전 복원

- **방법**: 6-3에서 비활성 `version_id`를 골라 Request body에 `{"version_id": <id>, "restored_by": "tester"}` + `x-admin-api-key` → Execute
- **기대**: `200` `{"message": "... 복원되었습니다."}` → 5-2 재조회 시 `version_id`가 바뀜
- **확인 포인트**: 버전은 불변이므로 원래 버전으로 다시 복원(왕복)해도 데이터 손실 없음
- **음성 케이스**: 다른 레슨의 version_id 또는 없는 id → `404`

### 6-5. `POST /api/v1/admin/generations/{id}/activate` — 세대 단위 일괄 전환

- **방법**: 6-1에서 completed 세대 `id` 선택 + `x-admin-api-key` → Execute
- **기대**: `200` → 5-1/5-2가 해당 세대의 레슨·버전으로 바뀜 (해당 세대에 없는 레슨은 목록에서 숨김)
- **음성 케이스**: 버전 없는 세대 → `400`, 없는 세대 → `404`

---

## 7. 권장 테스트 순서 요약

1. **무비용 스모크**: 2-1 → 2-2 → 3-1(React=141) → 5-1 → 5-2
2. **인증 검증**: 6-1을 키 없이(401) / 잘못된 키로(401) / 올바른 키로(200)
3. **버전/세대 관리** (세대 2개 이상일 때): 6-1 → 6-3 → 6-4(왕복) → 6-5(왕복)
4. **생성 파이프라인** (비용 발생 결정 후): 4-1 실행 → 서버 로그·6-1 모니터링 → 완료 후 5-1·5-2로 새 세대 확인
