# 레슨 저장소 DB 이관 — 작업 체크리스트 (detail_tasks)

> 상세 설계·근거: [DB_MIGRATION_PLAN.md](./DB_MIGRATION_PLAN.md) / Phase 구분·DoD: [db_detail.md](./db_detail.md)
>
> 각 Phase 완료 시 해당 커밋 1개 생성 (메시지는 db_detail.md 커밋 전략 참고).

## 진행 현황

- [x] **Phase 0** — 사전 정리 (선행 커밋 + 브랜치 + 환경 확인)
- [x] **Phase 1** — alembic 도입 + baseline
- [x] **Phase 2** — 신규 모델 3종 + 테스트 인프라
- [x] **Phase 3** — 조회 API `/lessons` + 48개 import
- [x] **Phase 4** — 생성 파이프라인 DB 전환
- [x] **Phase 5** — 관리자 세대/버전 API
- [ ] **Phase 6** — 프론트 전환
- [ ] **Phase 7** — 정리 (구 API 제거 + 문서)

---

## Phase 0 — 사전 정리

### 구현
- [x] `feature/vector-pipeline`에 커밋 1: `fix: Qdrant Cloud sub_category 필터링용 keyword payload 인덱스 추가` (index_data.py) — `7b694fb` (기 커밋 확인)
- [x] 커밋 2: `docs: Phase 6 실 인덱싱/시딩 완료 및 Phase 0-5 체크리스트 실측 재검증 반영` (tasks.md) — `cbc5ad6`
- [x] 커밋 3: `docs: Swagger 관리자 API 수동 테스트 가이드 및 결과 기록` (swagger_test_guide.md, swagger_test_results.md) — `09dc339`
- [x] `git checkout -b feature/lesson-db-migration` 브랜치 생성 (사용자 기 생성 확인)
- [x] PostgreSQL 기동 (`docker compose up -d`) 및 healthy 확인 — learnsphere-postgres Up 8h (healthy)
- [x] 실행 중인 uvicorn 프로세스가 이 워크스페이스(`C:\WorkSpace\learnshpere\learnsphere-api`) 기준인지 확인, 다른 복사본이면 중지 — 실행 중인 uvicorn/python 프로세스 없음 확인
- [x] 정본 데이터 확인: `C:\WorkSpace\generated_content`에 레슨 48개(초급22·중급14·고급12) + index.json — 실측 일치

### 검증 (DoD)
- [x] `git status` 클린 + 새 브랜치에서 시작
- [x] `.env`의 `DATABASE_URL`로 DB 접속 성공 — PostgreSQL 16.14 응답 확인

---

## Phase 1 — alembic 도입 + baseline

### 구현
- [x] `uv add alembic` — alembic 1.18.5
- [x] `alembic init alembic` 실행
- [x] `alembic/env.py` 수정: `load_dotenv()` → `DATABASE_URL`을 `config.set_main_option`으로 주입 (미설정 시 명시적 에러)
- [x] `alembic/env.py`: `from app.models import models` import 후 `target_metadata = Base.metadata` 지정
- [x] `0001_baseline` 마이그레이션 작성 (subjects, learning_content, lesson_backups 현행 그대로)
- [x] `app/main.py:21` `models.Base.metadata.create_all(bind=engine)` 제거 (+ 미사용 engine import 정리)
- [x] 기존 DB에 `uv run alembic stamp 0001` 적용
- [x] `README.md`에 기동 절차 추가 (서버 시작 전 `uv run alembic upgrade head`)

### 검증 (DoD)
- [x] 신규 빈 DB에서 `alembic upgrade head` → 3 테이블 생성 확인 (임시 DB alembic_check로 실증 후 삭제)
- [x] 기존 DB에서 `alembic current` → `0001 (head)` 표시
- [x] 서버 기동 + `/api/health` 200 (동작 무변화). `/lesson/index`는 404 — 이 복사본에 generated_content가 없는 기존 동작으로 Phase 1과 무관 (Phase 3에서 DB 기반으로 대체)
- [x] pytest 기존 26개 통과 (주의: uv 트램폴린 오류로 `.venv\Scripts\python.exe -m pytest`로 실행. 경고 경로에 `C:\WorkSpace\learnsphere-api` 노출 — 과거 위치의 stale 캐시/복사본 존재 정황)

---

## Phase 2 — 신규 모델 + 테스트 인프라

### 구현
- [x] `app/models/models.py`: `LessonGeneration` 모델 추가 (source/status/created_by/prompt/params/started_at/completed_at/total_topics/succeeded/failed_topics)
- [x] `app/models/models.py`: `Lesson` 모델 추가 (level/slug/topic/archived_at/created_at, UNIQUE(level, slug))
- [x] `app/models/models.py`: `LessonVersion` 모델 추가 (lesson_id/generation_id FK, title/position/core_concepts/code_examples/quizzes/is_current/created_at, UNIQUE(lesson_id, generation_id))
- [x] `LessonVersion`에 partial unique index (lesson_id WHERE is_current — `postgresql_where`/`sqlite_where` 병기)
- [x] 기존 `LessonBackup` 모델에 deprecated 주석 추가
- [x] `0002_lesson_content_tables` 마이그레이션 생성 및 적용
- [x] `app/schemas/schemas.py`: `CodeExample`, `Quiz`, `LessonContentSchema`(core_concepts min_length=1), `LessonSummary`, `LessonDetail` 추가 (기존 `class Config: from_attributes` 컨벤션)
- [x] `app/crud/crud_lessons.py` 신설: `slugify(topic)` (기존 safe_title 로직 + lower)
- [x] `crud_lessons.py`: `upsert_lesson`, `insert_version` 구현
- [x] `crud_lessons.py`: `finalize_generation` 구현 (단일 트랜잭션 — is_current 전환 + archived 처리 + 부분 실패 허용)
- [x] `crud_lessons.py`: `get_lesson_index`, `get_lesson_detail` 구현
- [x] `crud_lessons.py`: `restore_version`, `activate_generation` 구현 (+ 세대 관리 `create_generation`/`get_running_generation`/`fail_generation` 등)
- [x] `tests/conftest.py` 신설: app import 전 `os.environ.setdefault("DATABASE_URL", "sqlite://")`
- [x] `conftest.py`: in-memory SQLite + StaticPool `db_session` fixture
- [x] `conftest.py`: `dependency_overrides[get_db]` TestClient fixture + `ADMIN_API_KEY` 환경 변수 고정 (+ dev 의존성 httpx 추가)
- [x] `tests/test_lessons_crud.py` 작성 — 13개 테스트

### 검증 (DoD)
- [x] PostgreSQL 실 DB에 신규 3 테이블 + partial index 생성 확인 (`uq_lesson_versions_current ... WHERE is_current` 실증)
- [x] upsert 멱등성 테스트 통과 (같은 level+slug 재호출 시 중복 생성 없음)
- [x] is_current 유일성 테스트 통과 (동일 lesson에 current 2개 시도 → IntegrityError)
- [x] finalize 테스트 통과 (전환/archived/부분 실패 유지/전체 실패 무영향)
- [x] pytest 전체 39개 통과 (기존 26 + 신규 13, 기존 앱 동작 무변화)

---

## Phase 3 — 조회 API + import

### 구현
- [x] `app/api/lesson_api.py`: `GET /api/v1/lessons` 추가 (is_current JOIN, archived 제외, level·position 정렬, `{레벨: [{id,title,number}]}` 형태)
- [x] `lesson_api.py`: `GET /api/v1/lessons/{lesson_id}` 추가 (없거나 archived → 404, `response_model_exclude_none`으로 원본 충실 응답)
- [x] 구 `/lesson/index`, `/lesson/{filename}`은 유지 (공존)
- [x] `app/scripts/import_lessons_from_files.py` 신설: argparse (`--content-dir` 필수, `--created-by` 기본 'import', `--force`)
- [x] import: 파일명 `{level}_{NN}_{slug}.json` 파싱 (index.json·backup/ 제외, 레벨 화이트리스트 검증)
- [x] import: 본문 `LessonContentSchema` 검증, 실패 파일 목록 출력 + 전체 rollback
- [x] import: generation(source='import') + lessons + versions 생성 → `finalize_generation`
- [x] import: lessons 테이블 비어있지 않으면 `--force` 없이는 abort
- [x] import 실행: 48개 이관 완료. **이관 중 발견/수정**: 퀴즈 33건의 `explanation` 필드가 스키마에 없어 유실됨 → `Quiz.explanation` Optional 추가 + `model_dump(exclude_none=True)` 저장 후 `--force` 재이관으로 해결
- [x] `tests/test_lessons_api.py` 작성 (목록 구조/정렬, 상세 필드, 404, archived 숨김 — 5개)
- [x] `tests/test_import_script.py` 작성 (성공/rollback/abort/explanation 보존 — 6개)

### 검증 (DoD)
- [x] `GET /api/v1/lessons` → 초급22·중급14·고급12 반환 (실 서버 확인)
- [x] 상세 1건(초급_01_Editor-Setup)을 원본 JSON 파일과 필드 대조 — 완전 일치 (explanation 포함)
- [x] 구 API 라우트 공존 확인 (이 복사본엔 파일이 없어 404 — 기존 동작 그대로, 프론트 무영향)
- [x] pytest 전체 50개 통과

---

## Phase 4 — 생성 파이프라인 DB 전환

### 구현
- [x] `app/services/openai_service.py`: 에러-레슨 삼킴(94-103행) 제거 → `LessonGenerationError` raise
- [x] `openai_service.py`: `normalize_lesson` 후 `LessonContentSchema.model_validate` 검증 (실패 시 raise, `exclude_none` 반환)
- [x] `app/services/content_pipeline_service.py`: `OUTPUT_DIR`/`BACKUP_DIR`, 파일 쓰기/백업 복사, LessonBackup 기록, `create_index_file()` 제거 (전면 재작성)
- [x] `content_pipeline_service.py`: `run_full_content_generation(generation_id)` 재작성 — 토픽별 try/except 실패 집계, 성공 시 upsert + version insert(is_current=False), 레슨 단위 커밋
- [x] `content_pipeline_service.py`: 완료 시 `finalize_generation` 호출, 최상위 예외 시 status='failed' (+ 409 가드용 `request_full_generation` 헬퍼)
- [x] `app/api/admin_api.py`: `POST /admin/generate-all-content` — generation 행 생성(running 존재 시 409), generation_id를 BackgroundTask에 전달, `{message, generation_id}` 반환
- [x] `admin_api.py`: generate 엔드포인트 `Depends(get_db)` 전환 (구 백업 엔드포인트는 Phase 5에서 제거 예정이라 유지)
- [x] `app/main.py:68` 웹훅을 동일 헬퍼(`request_full_generation`)로 수정
- [x] `tests/test_pipeline_db.py` 작성 (qdrant/openai 모킹 e2e — 6개)

### 검증 (DoD)
- [x] generate 트리거 → lesson_generations에 running 행 생성 + `{message, generation_id}` 반환 (테스트)
- [x] 진행 중 `GET /lessons`가 이전 세대 유지 → 완료 후 새 세대 전환 (테스트)
- [x] 부분 실패 시 실패 레슨 구버전 유지 + failed_topics 기록 (테스트)
- [x] 검증 실패 토픽이 버전으로 저장되지 않음 — 에러 삼킴 회귀 방지 (테스트)
- [x] 중복 트리거 시 409 (테스트) + 전체 실패 시 status='failed'·현행 유지 (테스트)
- [x] pytest 전체 56개 통과. 실 서버 기동 + 401 인증 확인 (실 LLM 트리거는 비용 문제로 모킹 검증으로 갈음)

---

## Phase 5 — 관리자 세대/버전 API

### 구현
- [x] `admin_api.py`: `GET /admin/generations` (목록 — id/source/status/시각/created_by/succeeded/실패 수)
- [x] `admin_api.py`: `GET /admin/generations/{id}` (상세 + failed_topics)
- [x] `admin_api.py`: `POST /admin/generations/{id}/activate` (세대 일괄 전환, archived 해제 포함 — 빈 세대 400, 없는 세대 404)
- [x] `admin_api.py`: `GET /admin/lessons/{lesson_id}/versions` (버전 목록, source 포함)
- [x] `admin_api.py`: `POST /admin/lessons/{lesson_id}/restore` (`{version_id, restored_by?}` → is_current 이동)
- [x] 구 백업 엔드포인트 4종 제거 (lesson-backups, restore-lesson-backup, backup-list, restore-backup-date)
- [x] `OUTPUT_DIR`/`BACKUP_DIR` 상수 제거 + 미사용 import(os/re/shutil/datetime/SessionLocal/LessonBackup) 정리
- [x] `tests/test_lessons_api.py` 확장 — 세대 목록/상세, activate 전환, 버전 목록/복원, 인증 4개 엔드포인트 401 (4개 추가)

### 검증 (DoD)
- [x] 실 서버: 버전 목록 → 과거 버전(gen1) restore → version_id 확인 → 재복원 왕복 성공 (원상 복귀 완료)
- [x] activate로 generation 1 ↔ 2 전환 동작 (실 서버 왕복 확인)
- [x] admin 키 없이 호출 시 401, 키 포함 시 200 (테스트 + 실 서버)
- [x] pytest 전체 60개 통과

---

## Phase 6 — 프론트 전환

### 구현
- [ ] `src/api/axios.ts`: `baseURL: import.meta.env.VITE_API_BASE_URL ?? ''`, `withCredentials` 제거
- [ ] `src/api/lessonApi.ts`: 하드코딩 `http://127.0.0.1:8000` 제거, 전 함수 axios 인스턴스로 통일
- [ ] `lessonApi.ts`: 타입 갱신 — `LessonSummary {id,title,number}`, `LessonDetail`(id/version_id/updated_at 포함)
- [ ] `lessonApi.ts`: `fetchLessonIndex()` → `GET /lessons`, `fetchLessonDetail(id: number)` → `GET /lessons/{id}`
- [ ] `lessonApi.ts`: 백업 함수 4개 삭제 → `fetchGenerations`/`activateGeneration`/`fetchLessonVersions`/`restoreLessonVersion` 신설
- [ ] `lessonApi.ts`: `setAdminApiKey(key)` — sessionStorage 저장 + 요청 인터셉터로 `X-Admin-API-Key` 자동 첨부
- [ ] `src/pages/ReactLearnPage.tsx`: `filename` 참조 → `id` 치환 (132, 151, 218-219행 등), 렌더링 본문 무변경
- [ ] `src/pages/AdminPanel.tsx`: 관리자 키 입력 필드 (미입력 시 admin 버튼 disable)
- [ ] `AdminPanel.tsx`: 날짜별 백업 패널 → 세대 패널 (목록/전환/실패 토픽 표시)
- [ ] `AdminPanel.tsx`: 레슨 백업 패널 → 버전 패널 (datalist: 표시 title·값 lesson id → 버전 목록/복원)

### 검증 (DoD)
- [ ] 학습 페이지: 레벨 전환·레슨 카드·상세(core_concepts/code_examples/quizzes) 렌더링 정상
- [ ] AdminPanel: 키 입력 후 생성 트리거 성공 — 401 버그 해소 확인
- [ ] AdminPanel: 세대 목록/전환, 버전 목록/복원 e2e
- [ ] `npm run build` (tsc) 통과 — filename 참조 잔존 시 타입 에러로 검출

---

## Phase 7 — 정리

### 구현
- [ ] `lesson_api.py`: 구 `/lesson/index`, `/lesson/{filename}`, `CONTENT_DIR`, `resolve_lesson_path` 제거
- [ ] `main.py:43-45`: StaticFiles `/static/content` 마운트 제거
- [ ] `app/scripts/migrate_backup_to_datefolders.py` 삭제
- [ ] `ARCHITECTURE.md` 갱신 (저장 구조: 파일 → PG 3 테이블, 엔드포인트 표 교체)
- [ ] `README.md`, `PROCESS_AND_RUN.md` 갱신 (alembic 절차, import 사용법)
- [ ] `swagger_test_guide.md` 갱신 (신 엔드포인트 목록)
- [ ] `C:\WorkSpace\generated_content` 아카이브 처리 방침 확정 (사용자 판단)

### 검증 (DoD)
- [ ] app 코드에서 `generated_content` 참조 0 (grep 확인, 문서·아카이브 언급 제외)
- [ ] `uv run pytest` 전체 통과 + `npm run build` 통과
- [ ] 서버 기동 후 학습/관리 화면 스모크 테스트
- [ ] 구 엔드포인트 호출 시 404 확인
