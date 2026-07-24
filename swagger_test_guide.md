# Swagger 테스트 가이드

FastAPI가 자동 생성하는 Swagger UI(`/docs`)로 LearnSphere API를 수동 테스트하는 방법을 정리한다. 각 시나리오는 **호출 방법 → 기대 결과 → 확인 포인트** 순으로 기술한다.

> 관련 문서: [plan.md](./plan.md) · [tasks.md](./tasks.md)

## 1. 사전 준비

| 항목 | 명령/확인 |
|---|---|
| PostgreSQL 기동 | `docker compose up -d` → `docker compose ps`에서 `learnsphere-postgres`가 `healthy` |
| `.env` 확인 | `DATABASE_URL`, `QDRANT_URL`, `QDRANT_API_KEY`, `OPENAI_API_KEY`, `ADMIN_API_KEY` 설정 |
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

> ⚠️ gpt-4o-mini 48회 호출(초급22·중급14·고급12), 입력 약 42만 토큰 + 출력 약 6~12만 토큰 ≈ **$0.10~0.14**. 기존 레슨 파일이 있으면 자동 백업 후 덮어쓴다.

- **방법**: `x-admin-api-key` 입력 → Execute
- **기대**: 즉시 `200` `{"message": "전체 콘텐츠 생성 작업이 백그라운드에서 시작되었습니다. ..."}`
- **확인 포인트**:
  - 응답은 즉시 오고 실제 생성은 백그라운드 진행 — **uvicorn 서버 로그**에서 `[Processing i/22] ... 레슨 생성 중` 진행 상황 확인
  - 완료 후 프로젝트 상위의 `generated_content/`에 `초급_01_*.json` ~ `고급_12_*.json` 48개 + `index.json` 생성
  - 소요 시간: 호출당 수십 초 × 48회 → 수십 분 수준

### 4-2. `POST /api/v1/webhooks/content-updated` — 웹훅 (Webhooks 태그)

4-1과 동일한 파이프라인을 트리거하는 별칭 엔드포인트. 같은 방법·같은 비용 주의.

---

## 5. 생성된 레슨 조회 (Lesson 태그, 인증 불필요)

> 4번 실행 전에는 모두 `404`가 정상이다.

### 5-1. `GET /api/v1/lesson/index` — 레슨 인덱스

- **방법**: Try it out → Execute
- **기대(생성 전)**: `404 {"detail": "인덱스 파일을 찾을 수 없습니다. ..."}`
- **기대(생성 후)**: `200`, `{"초급": [{filename, title, number}, ...], "중급": [...], "고급": [...]}`

### 5-2. `GET /api/v1/lesson/{filename}` — 개별 레슨

- **방법**: 5-1 응답에서 `filename` 하나를 복사해 입력 (예: `초급_01_Add-React-To-An-Existing-Project.json`) → Execute
- **기대**: `200`, 스키마 `{title, level, core_concepts, code_examples[], quizzes[]}`
- **음성 케이스**:
  - `..%2Fsecret.json`처럼 경로 구분자 포함 또는 `.json` 미종료 파일명 → `400` (경로 탈출 방어)
  - 존재하지 않는 파일명 → `404`

---

## 6. 백업/복원 (Admin)

> 백업은 레슨 **재생성 시** 자동 생성되므로, 4-1을 두 번 이상 실행한 뒤에 테스트해야 데이터가 있다.

### 6-1. `GET /api/v1/admin/backup-list` — 날짜별 백업 목록

- **방법**: `x-admin-api-key` 입력 → Execute
- **기대**: `200`, `{"YYYY-MM-DD": ["초급_01_..._20260724_153000.json", ...]}` (백업 없으면 빈 객체 `{}`)

### 6-2. `GET /api/v1/admin/lesson-backups` — 특정 레슨의 백업 이력

- **방법**: `lesson_filename`에 레슨 파일명(예: `초급_01_....json`) + `x-admin-api-key` 입력 → Execute
- **기대**: `200`, `[{id, lesson_filename, backup_filename, created_at, created_by, action}, ...]` (action: `backup`/`create`/`restore` 등)

### 6-3. `POST /api/v1/admin/restore-lesson-backup` — 백업 복원

- **방법**: 6-2 응답에서 `id`를 골라 Request body에 `{"backup_id": <id>, "restored_by": "tester"}` + `x-admin-api-key` 입력 → Execute
- **기대**: `200` `{"message": "... 백업본으로 복원되었습니다."}`
- **확인 포인트**: 복원 직전 현재 파일도 `backup-before-restore` action으로 자동 백업됨 (6-2 재조회로 확인)
- **음성 케이스**: 없는 `backup_id` → `404`

### 6-4. `POST /api/v1/admin/restore-backup-date` — 날짜 단위 일괄 복원

- **방법**: Request body에 `{"date": "YYYY-MM-DD"}` (6-1에 존재하는 날짜) + `x-admin-api-key` 입력 → Execute
- **기대**: `200`, `{"restored": [원본 파일명 목록], "message": ...}`
- **음성 케이스**: 없는 날짜 → `404`, `../` 포함 값 → `400`

---

## 7. 권장 테스트 순서 요약

1. **무비용 스모크**: 2-1 → 2-2 → 3-1(React=141) → 5-1(생성 전 404 확인)
2. **인증 검증**: 6-1을 키 없이(401) / 잘못된 키로(401) / 올바른 키로(200)
3. **생성 파이프라인** (비용 발생 결정 후): 4-1 실행 → 서버 로그 모니터링 → 5-1·5-2로 결과 조회
4. **백업/복원**: 4-1 재실행으로 백업 생성 → 6-1 → 6-2 → 6-3 → 6-4
