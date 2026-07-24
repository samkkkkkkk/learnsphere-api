# 레슨 저장소 DB 이관 — 단계별 상세 계획 (db_detail)

> 원칙: **가장 단순하게 동작하는 것부터** 만들고, 각 Phase마다 검증을 통과시킨 뒤 다음 기능을 얹는다. Phase 3까지는 기존 파일 API가 무손상으로 공존하므로 언제든 롤백 가능하며, 구 API 제거는 프론트 전환이 끝난 마지막 Phase에서만 수행한다.
>
> 상위 설계·근거는 [DB_MIGRATION_PLAN.md](./DB_MIGRATION_PLAN.md) 참고. 이 문서는 실행 순서와 완료기준(DoD)에 집중한다.

## 진행 개요

| Phase | 한 줄 목표 | 새 기능 | 동작 변화 |
|---|---|---|---|
| 0 | 사전 정리 (선행 커밋 + 브랜치 + 환경 확인) | 준비 | 없음 |
| 1 | alembic 도입 + baseline | 마이그레이션 체계 | 없음 (기동 절차만 변경) |
| 2 | 신규 모델 3종 + 테스트 인프라 | 데이터 계층 | 없음 (빈 테이블만 생성) |
| 3 | 조회 API `/lessons` + 48개 import | 읽기 경로 | 신 API 추가 (구 API 공존) |
| 4 | 생성 파이프라인 DB 전환 | 쓰기 경로 | generate가 DB에 기록 |
| 5 | 관리자 세대/버전 API | 관리 기능 | admin API 교체 |
| 6 | 프론트 전환 | 프론트 | 프론트가 신 API 사용 |
| 7 | 정리 (구 API 제거 + 문서) | 클린업 | 구 API 제거 |

---

## Phase 0 — 사전 정리

**목표:** 코드 변경 없이 작업 기반만 확보.

**작업**
- `feature/vector-pipeline`에 미커밋 3건 커밋 (메시지 확정됨: index_data.py fix / tasks.md docs / swagger 문서 docs).
- `git checkout -b feature/lesson-db-migration` 브랜치 분기.
- PostgreSQL 기동 확인 (`docker compose up -d`, `docker compose ps`에서 healthy).
- **실행 중인 uvicorn이 이 워크스페이스 복사본인지 확인** — 과거 다른 복사본(`C:\WorkSpace\learnsphere-api` 추정)이 돌던 정황 있음. 다른 복사본이면 중지.
- 정본 데이터 확인: `C:\WorkSpace\generated_content`에 레슨 48개(초급22·중급14·고급12) + index.json 존재.

**검증 / DoD**
- `git status` 클린, 새 브랜치에서 작업 시작.
- `.env`의 `DATABASE_URL`로 psql/pgAdmin 접속 성공.

---

## Phase 1 — alembic 도입 + baseline (동작 무변화)

**목표:** 스키마 버전 관리 체계를 세우되, 앱 동작은 그대로.

**작업**
- `uv add alembic` → `alembic init alembic`.
- `alembic/env.py`: `load_dotenv()` 후 `DATABASE_URL`을 `config.set_main_option`으로 주입, `from app.models import models` import 후 `target_metadata = Base.metadata`.
- `0001_baseline` 마이그레이션: 기존 3 테이블(subjects, learning_content, lesson_backups) 그대로.
- `app/main.py:21`의 `models.Base.metadata.create_all(bind=engine)` 제거.
- **기존 DB**는 `uv run alembic stamp 0001`로 baseline 처리 (테이블이 이미 존재하므로).
- README.md에 기동 절차 추가: 서버 시작 전 `uv run alembic upgrade head`.

**검증 / DoD**
- 신규 빈 DB에 `alembic upgrade head` → 3 테이블 생성 확인.
- 기존 DB에 `alembic stamp 0001` → `alembic current`가 0001 표시.
- 서버 기동 + 기존 API(`/api/health`, `/api/v1/lesson/index`) 정상 — **동작 변화 없음 확인**.
- `uv run pytest` 기존 26개 통과.

---

## Phase 2 — 신규 모델 + 테스트 인프라 (미사용 테이블)

**목표:** 데이터 계층만 먼저 완성. 아무 API도 사용하지 않는 빈 테이블 상태.

**작업**
- `app/models/models.py`에 3 모델 추가 (스키마 상세는 DB_MIGRATION_PLAN.md §3):
  - `LessonGeneration` — 생성 배치(세대): source/status/created_by/prompt/params/시각/통계/failed_topics.
  - `Lesson` — 정체성: level/slug/topic/archived_at, **UNIQUE(level, slug)**.
  - `LessonVersion` — 불변 본문: title/position/core_concepts/code_examples/quizzes/is_current, UNIQUE(lesson_id, generation_id) + **partial unique index**(lesson_id WHERE is_current, postgresql_where/sqlite_where 병기).
  - 기존 `LessonBackup`에 deprecated 주석.
- `0002_lesson_content_tables` 마이그레이션 생성·적용.
- `app/schemas/schemas.py`에 추가: `CodeExample`, `Quiz`, `LessonContentSchema`(생성 검증·import 공용, core_concepts `min_length=1`), `LessonSummary`, `LessonDetail` — 기존 `class Config: from_attributes` 컨벤션.
- `app/crud/crud_lessons.py` 신설 (함수형): `slugify(topic)`(기존 safe_title 로직 + lower), `upsert_lesson`, `insert_version`, `finalize_generation`, `get_lesson_index`, `get_lesson_detail`, `restore_version`, `activate_generation`.
- `tests/conftest.py` 신설: `os.environ.setdefault("DATABASE_URL", "sqlite://")`를 **app import 전** 설정, in-memory SQLite + StaticPool `db_session` fixture, `dependency_overrides[get_db]` TestClient, `ADMIN_API_KEY` monkeypatch.
- `tests/test_lessons_crud.py`: 모델/CRUD 단위 테스트.

**검증 / DoD**
- `alembic upgrade head` → 신규 3 테이블 + partial index 생성 (PostgreSQL 실 확인).
- CRUD 테스트 통과: upsert 멱등성, is_current 유일성(위반 시 IntegrityError), finalize의 전환/archived 로직 (SQLite로 검증).
- 기존 앱 동작 무변화 (`uv run pytest` 전체 통과).

---

## Phase 3 — 조회 API + import (읽기 경로 완성)

**목표:** 신규 API로 레슨을 **읽을 수 있는** 상태. 구 파일 API와 공존 — 데이터는 일회성 import로 적재.

**작업**
- `app/api/lesson_api.py`에 신규 엔드포인트 추가 (구 `/lesson/*`은 유지, 경로가 `/lessons/*`라 충돌 없음):
  - `GET /api/v1/lessons` → `{ "초급": [{id, title, number}], ... }` (is_current JOIN, archived 제외, level·position 정렬).
  - `GET /api/v1/lessons/{lesson_id}` → `{id, level, title, core_concepts, code_examples, quizzes, version_id, updated_at}`, 없거나 archived면 404.
- `app/scripts/import_lessons_from_files.py` 신설: argparse(`--content-dir` 필수, `--created-by`, `--force`), 파일명 `{level}_{NN}_{slug}.json` 파싱 → `LessonContentSchema` 검증 → generation(source='import') + lessons + versions → `finalize_generation`. 실패 파일 존재 시 전체 rollback.
- import 실행: `uv run python -m app.scripts.import_lessons_from_files --content-dir "C:\WorkSpace\generated_content"`.
- `tests/test_lessons_api.py`(목록/상세/404), `tests/test_import_script.py`(성공/rollback/abort — tmp_path 샘플).

**검증 / DoD**
- import 후 `GET /api/v1/lessons`가 초급22·중급14·고급12 반환.
- 상세 1건을 원본 JSON 파일과 필드 대조 — 일치.
- 구 API(`/lesson/index`, `/lesson/{filename}`)도 여전히 정상 (프론트 무영향).
- 신규 테스트 + 기존 테스트 전체 통과.

---

## Phase 4 — 생성 파이프라인 DB 전환 (쓰기 경로)

**목표:** generate가 파일 대신 DB에 쓰고, 세대 단위 원자적 전환이 동작.

**작업**
- `app/services/openai_service.py`: 에러-레슨 삼킴(94-103행) 제거 → `LessonGenerationError` raise, `normalize_lesson` 후 `LessonContentSchema.model_validate` 검증.
- `app/services/content_pipeline_service.py` 전면 재작성:
  - 제거: `OUTPUT_DIR`/`BACKUP_DIR`, 파일 쓰기/백업 복사, LessonBackup 기록, `create_index_file()`.
  - `run_full_content_generation(generation_id)`: 토픽별 try/except로 실패 집계, 성공 시 upsert + version insert(is_current=False), 완료 시 `finalize_generation`(단일 트랜잭션: is_current 전환 + archived 처리 + 부분 실패 허용), 최상위 예외 시 status='failed'.
- `app/api/admin_api.py`의 `POST /admin/generate-all-content`: generation 행 생성(running 존재 시 **409**) 후 generation_id를 BackgroundTask에 전달, `{message, generation_id}` 반환. `SessionLocal()` 직접 생성 → `Depends(get_db)` 전환.
- `app/main.py:68` 웹훅도 동일 헬퍼로 수정.
- `tests/test_pipeline_db.py`: qdrant/openai 모킹 e2e — running 중 구버전 유지 → finalize 후 신버전, 부분 실패 시 구버전 유지 + 미포함 레슨 archived, 검증 실패 토픽이 저장 안 되고 failed_topics 기록.

**검증 / DoD**
- Swagger에서 admin 키로 generate 트리거 → lesson_generations에 running 행, 진행 중 `GET /lessons`가 이전 세대 유지, 완료 후 새 세대로 전환 확인 (실 LLM 1회 또는 모킹).
- 중복 트리거 시 409.
- 구 백업 엔드포인트 4종은 이 Phase에서는 방치 (파일을 더 이상 쓰지 않으므로 기능적으로 무의미하나, 이미 프론트에서 401로 불능 — 제거는 Phase 5).
- 신규 테스트 + 기존 테스트 전체 통과.

---

## Phase 5 — 관리자 세대/버전 API (관리 기능)

**목표:** 백업/복원을 DB 버전 체계로 대체.

**작업**
- `app/api/admin_api.py`에 신규 엔드포인트:
  - `GET /admin/generations` — 세대 목록 (id/source/status/시각/created_by/succeeded/실패 수).
  - `GET /admin/generations/{id}` — 상세 + failed_topics.
  - `POST /admin/generations/{id}/activate` — 세대 일괄 전환(트랜잭션, archived 해제 포함). 구 restore-backup-date 대체.
  - `GET /admin/lessons/{lesson_id}/versions` — 버전 목록. 구 lesson-backups 대체.
  - `POST /admin/lessons/{lesson_id}/restore` — `{version_id, restored_by?}` → is_current 이동. 구 restore-lesson-backup 대체.
- 구 백업 엔드포인트 4종(lesson-backups, restore-lesson-backup, backup-list, restore-backup-date) + `OUTPUT_DIR`/`BACKUP_DIR` 상수 제거.
- `tests/test_lessons_api.py` 확장: restore/activate/is_current 유일성, admin 인증 401/200.

**검증 / DoD**
- Swagger에서 버전 목록 조회 → 과거 버전으로 restore → `GET /lessons/{id}`가 복원된 본문 반환 → 다시 최신으로 restore (불변 버전이라 왕복 가능).
- activate로 import 세대 ↔ pipeline 세대 전환 동작.
- 신규 테스트 + 기존 테스트 전체 통과.

---

## Phase 6 — 프론트 전환

**목표:** 프론트가 ID 기반 신 API만 사용하고, admin 인증 버그 해소.

**작업**
- `src/api/axios.ts`: `baseURL: import.meta.env.VITE_API_BASE_URL ?? ''`(상대경로 → Vite proxy), `withCredentials` 제거.
- `src/api/lessonApi.ts`: 하드코딩 URL + raw axios/fetch 혼용 제거 → axios 인스턴스 통일. `fetchLessonIndex()`→`GET /lessons`, `fetchLessonDetail(id: number)`→`GET /lessons/{id}`. 백업 함수 4개 삭제 → `fetchGenerations`/`activateGeneration`/`fetchLessonVersions`/`restoreLessonVersion` 신설. `setAdminApiKey(key)` — sessionStorage 저장 + 요청 인터셉터가 `X-Admin-API-Key` 자동 첨부 (env 주입은 번들 평문 노출이라 비권장).
- `src/pages/ReactLearnPage.tsx`: `filename` 참조를 `id`로 치환 (132, 151, 218-219행 등). 렌더링 본문 무변경.
- `src/pages/AdminPanel.tsx`: 관리자 키 입력 필드(미입력 시 admin 버튼 disable), 날짜별 백업 패널 → **세대 패널**(목록/전환/실패 토픽), 레슨 백업 패널 → **버전 패널**(datalist: 표시 title·값 lesson id → 버전 목록/복원).

**검증 / DoD**
- 프론트 dev 서버에서 학습 페이지: 레벨 전환·레슨 카드·상세(core_concepts/code_examples/quizzes) 렌더링 정상.
- AdminPanel: 키 입력 후 생성 트리거 성공(401 버그 해소 확인), 세대 목록/전환, 버전 목록/복원 e2e.
- `npm run build` (tsc) 통과 — filename 참조 잔존 시 타입 에러로 검출.

---

## Phase 7 — 정리 (클린업)

**목표:** 파일 기반 잔재 제거, 문서 정합.

**작업**
- 제거: `lesson_api.py`의 구 `/lesson/index`·`/lesson/{filename}`·`CONTENT_DIR`·`resolve_lesson_path`, `main.py:43-45` StaticFiles 마운트, `app/scripts/migrate_backup_to_datefolders.py`.
- 문서 갱신: `ARCHITECTURE.md`(저장 구조 다이어그램: 파일 → PG 3 테이블, 엔드포인트 표 교체), `README.md`·`PROCESS_AND_RUN.md`(alembic 절차, import 사용법), `swagger_test_guide.md`(신 엔드포인트).
- `C:\WorkSpace\generated_content`는 **아카이브로 보존** (코드 참조 0 확인 후 이동/보관은 사용자 판단).

**검증 / DoD**
- `grep generated_content` — app 코드에서 참조 0 (문서·아카이브 언급 제외).
- 전체 테스트 통과 + 프론트 build 통과 + 서버 기동 후 학습/관리 화면 스모크.
- 구 엔드포인트 호출 시 404 확인.

---

## 커밋 전략(권장)

Phase당 1커밋, 기존 컨벤션(`타입: 한글 설명`) 유지. 커밋은 사용자 승인 후 수행.

| Phase | 커밋 메시지 예시 |
|---|---|
| 1 | `build: alembic 도입 및 기존 스키마 baseline 마이그레이션` |
| 2 | `feat: 레슨 세대/버전 모델·스키마·CRUD 및 DB 테스트 인프라 추가` |
| 3 | `feat: ID 기반 레슨 조회 API 및 파일 레슨 일회성 import 스크립트` |
| 4 | `feat: 콘텐츠 생성 파이프라인 DB 전환 - 세대 원자 전환 및 생성 시점 검증` |
| 5 | `feat: 관리자 세대/버전 API - 파일 백업 엔드포인트 대체` |
| 6 | `feat: 프론트 ID 기반 API 전환 및 관리자 키 인증 UI` |
| 7 | `chore: 파일 기반 레슨 저장소 잔재 제거 및 문서 갱신` |

## 열린 결정 사항

- Phase 7의 `C:\WorkSpace\generated_content` 아카이브 최종 위치(그대로 두기 / 저장소 밖 별도 보관) — 사용자 판단.
- `lesson_backups` 테이블 drop 시점 — 이번 범위에서는 유지(deprecated), 추후 별도 결정.
