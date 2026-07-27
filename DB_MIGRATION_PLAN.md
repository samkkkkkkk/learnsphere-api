# 레슨 콘텐츠 저장소: 파일시스템 → PostgreSQL 이관 계획

> 작성일: 2026-07-24. `generated_content/` 파일 기반 레슨 저장소를 PostgreSQL로 이관하기 위한 실행 계획.

## 1. 배경 (왜 하는가)

현재 생성된 레슨(JSON 48개)은 프로젝트 루트 **밖**의 `generated_content/` 폴더에 파일로 저장되고, `index.json`은 디렉토리 스캔 + 파일명 파싱으로 만들어진다. 이 구조의 문제:

1. 저장 경로가 저장소 밖으로 계산되는 배포 취약성 (실제 데이터가 `C:\WorkSpace\generated_content`에 존재)
2. 재생성 시 구파일이 삭제되지 않아 인덱스 오염 (폐기 토픽이 목록에 잔존)
3. 비원자적 쓰기 — 중단 시 깨진 JSON, 조회 500
4. 전체 재생성(수 분) 중 신구 버전 혼재 노출
5. 진실의 원천 분열 — 본문은 파일, 백업 이력은 PostgreSQL(`lesson_backups`)

## 2. 확정 결정사항

| 항목 | 결정 |
|---|---|
| API 계약 | **ID 기반으로 전환** (`GET /lessons`, `GET /lessons/{id}`) — 프론트 수정 포함 |
| 기존 백업 | **새로 시작** — 활성 레슨 48개만 import, `backup/` 파일·`lesson_backups` 이력은 아카이브 보존만 |
| 마이그레이션 도구 | **alembic 도입** (기존 테이블 baseline 포함) |
| 프론트 인증 버그 | **포함** — `X-Admin-API-Key` 헤더 미전송(현재 admin 버튼 401) 수정 |
| 정본 데이터 | `C:\WorkSpace\generated_content` (레슨 48개 + index.json) |
| 범위 제외 | `validated_json_server.py` — `generated_content`와 무관한 레거시 독립 서버 |

## 3. DB 스키마 설계 (`app/models/models.py`에 추가)

### `lesson_generations` — 생성 배치(세대)

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | Integer PK | |
| source | String(20) | `'pipeline'` \| `'import'` |
| status | String(20) | `'running'` \| `'completed'` \| `'failed'` |
| created_by / prompt / params | String / Text / JSON | 기존 LessonBackup 필드 승계 |
| started_at / completed_at | DateTime | |
| total_topics / succeeded | Integer | |
| failed_topics | JSON | `[{"level","topic","error"}]` |

### `lessons` — 레슨 정체성 (본문 없음)

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | Integer PK | |
| level | String(20) | 초급/중급/고급 |
| slug | String(255) | topic 정규화 슬러그 |
| topic | String(255) | Qdrant 원본 토픽명 |
| archived_at | DateTime nullable | 새 세대에 없는 토픽 → 숨김(삭제 아님) |
| created_at | DateTime | |

- **UNIQUE(level, slug)** — 안정 키. 번호(`i:02d`)는 재생성마다 바뀔 수 있어 키에서 제외(표시용 `position`)
- slug는 기존 `safe_title` 정규화(`content_pipeline_service.py:36-37`) + lowercase 재사용 → 기존 파일명과 1:1 매칭되어 import 단순화

### `lesson_versions` — 불변 본문 (버전 = 세대 × 레슨)

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | Integer PK | |
| lesson_id / generation_id | FK | UNIQUE(lesson_id, generation_id) |
| title | String | |
| position | Integer | 세대 내 레벨별 순번 (프론트 number) |
| core_concepts | Text | |
| code_examples / quizzes | JSON | |
| is_current | Boolean | **partial unique index**(lesson_id WHERE is_current — postgresql_where/sqlite_where 병기) |
| created_at | DateTime | |

- 포인터 컬럼 대신 `is_current` 플래그 채택: 순환 FK 회피 + SQLite 테스트 호환
- 버전은 불변 — 복원은 덮어쓰기가 아니라 is_current 이동이므로 "복원 전 백업" 개념 자체가 불필요

### `lesson_backups` (기존)

유지하되 **deprecated** 주석 — 신규 쓰기 전부 제거. drop은 추후 별도 결정 (파일 아카이브와의 연결 고리 보존).

## 4. 핵심 동작 설계

### 세대 단위 원자적 전환

1. API 핸들러가 generation 행(status='running') 생성 후 `generation_id`를 BackgroundTask에 전달. running 세대 존재 시 **409** (중복 실행 가드)
2. 토픽별: LLM 호출 → `LessonContentSchema` 검증 → lessons upsert(level+slug) → versions insert(**is_current=False**) — 진행 중에도 사용자는 이전 세대만 봄
3. `finalize_generation(db, generation_id)` **단일 트랜잭션**: 새 버전 is_current 전환, 세대에 없는 레슨 `archived_at` 설정, **실패 토픽은 구버전 유지**(부분 성공 허용, failed_topics 기록), status='completed'
4. 전체 실패 시 status='failed', is_current 무변경 → 사용자 영향 없음

### 생성 시점 검증 (`openai_service.py`)

- 예외 시 에러 메시지를 core_concepts에 담아 정상 반환하는 삼킴 로직(94-103행) 제거 → `LessonGenerationError` raise
- `normalize_lesson` 후 `LessonContentSchema.model_validate` 검증(빈 core_concepts 거부). 실패는 failed_topics로 집계 — 에러 텍스트가 정식 레슨으로 저장되는 일 차단

## 5. API 재설계

### 공개 (`lesson_api.py` 교체) — 경로가 `/lesson/*` → `/lessons/*`라 신구 공존 가능

```
GET /api/v1/lessons
  → { "초급": [{id, title, number}], "중급": [...], "고급": [...] }
    (is_current JOIN, archived 제외, level·position 정렬 — 기존 index.json과 동일 형태)

GET /api/v1/lessons/{lesson_id}
  → { id, level, title, core_concepts, code_examples, quizzes, version_id, updated_at }
```

### 관리자 (`admin_api.py` 개편 — verify_admin_key 유지, `SessionLocal()` 직접 생성 → `Depends(get_db)` 통일)

```
POST /admin/generate-all-content            # 유지, {message, generation_id} 반환
GET  /admin/generations                     # 세대 목록
GET  /admin/generations/{id}                # 상세 + failed_topics
POST /admin/generations/{id}/activate       # 세대 일괄 전환 (구 restore-backup-date 대체)
GET  /admin/lessons/{lesson_id}/versions    # 버전 목록 (구 lesson-backups 대체)
POST /admin/lessons/{lesson_id}/restore     # {version_id, restored_by?} (구 restore-lesson-backup 대체)
```

- 제거: 백업 엔드포인트 4종, `OUTPUT_DIR`/`BACKUP_DIR` 상수, `main.py:43-45` StaticFiles 마운트(프론트 미사용)
- `main.py:68` 웹훅도 generation 생성 헬퍼 공용화로 수정
- 스키마(`schemas.py` 추가): `CodeExample`, `Quiz`, `LessonContentSchema`(생성 검증·import 공용), `LessonSummary`, `LessonDetail` — 기존 `class Config: from_attributes` 컨벤션 유지
- CRUD: `app/crud/crud_lessons.py` 신설 (함수형 컨벤션 — 조회/upsert/finalize/restore)

## 6. Alembic 셋업

- `uv add alembic` → `alembic init alembic`, `env.py`에서 dotenv 로드 후 `DATABASE_URL` 주입, `target_metadata = Base.metadata`
- 마이그레이션 2개:
  - `0001_baseline`: subjects, learning_content, lesson_backups (현행 그대로) — **기존 DB는 `alembic stamp 0001` 후 upgrade**, 신규 DB는 `upgrade head`만
  - `0002_lesson_content_tables`: 신규 3 테이블 + partial unique index
- `main.py:21`의 `create_all` **제거** → 기동 전 `uv run alembic upgrade head` 절차로 대체 (README/PROCESS_AND_RUN.md 문서화)

## 7. 일회성 Import 스크립트

`app/scripts/import_lessons_from_files.py` (신규):

- argparse: `--content-dir`(필수 — 하드코딩 금지), `--created-by`(기본 'import'), `--force`(lessons 비어있지 않으면 기본 abort)
- 파일명 `{level}_{NN}_{slug}.json` 파싱 → `LessonContentSchema` 검증 → generation(source='import') + lessons + versions → finalize
- 실패 파일 존재 시 **전체 rollback** (일회성이므로 all-or-nothing)
- 실행: `uv run python -m app.scripts.import_lessons_from_files --content-dir "C:\WorkSpace\generated_content"`

## 8. 프론트엔드 수정 (`learnsphere-frontend`)

| 파일 | 수정 내용 |
|---|---|
| `src/api/axios.ts` | `baseURL: import.meta.env.VITE_API_BASE_URL ?? ''` (상대경로 → Vite proxy), withCredentials 제거 |
| `src/api/lessonApi.ts` | 하드코딩 `http://127.0.0.1:8000` + raw axios/fetch 혼용 제거 → axios 인스턴스 통일. `fetchLessonIndex()`→`GET /lessons`, `fetchLessonDetail(id)`→`GET /lessons/{id}`. 백업 함수 4개 삭제 → `fetchGenerations`/`activateGeneration`/`fetchLessonVersions`/`restoreLessonVersion` 신설 |
| admin 키 주입 | env 방식은 번들에 평문 노출되어 **비권장** → AdminPanel에 키 입력 UI + sessionStorage 저장, 요청 인터셉터가 `X-Admin-API-Key` 자동 첨부 |
| `src/pages/ReactLearnPage.tsx` | `filename` 참조를 `id`로 치환 (132, 151, 218-219행 등). 렌더링 본문 무변경 |
| `src/pages/AdminPanel.tsx` | 키 입력 필드 추가, 날짜별 백업 패널 → **세대 패널**(목록/전환/실패 토픽), 레슨 백업 패널 → **버전 패널**(목록/복원) |

## 9. 테스트

**인프라** (`tests/conftest.py` 신규):
- `os.environ.setdefault("DATABASE_URL", "sqlite://")`를 **app import 전** 설정 (`database.py`가 import 시점에 create_engine 실행하므로)
- in-memory SQLite + StaticPool + create_all 기반 `db_session` fixture, `dependency_overrides[get_db]` TestClient, `ADMIN_API_KEY` monkeypatch

**핵심 테스트** (`test_lessons_api.py`, `test_pipeline_db.py`, `test_import_script.py`):
1. 목록/상세 구조·정렬, 404
2. 세대 running 중 구버전 유지 → finalize 후 신버전 노출 (원자적 전환)
3. 부분 실패: 실패 레슨 구버전 유지, 미포함 레슨 archived → 목록 제외
4. 버전 restore, 세대 activate(archived 해제 포함), is_current 유일성
5. 파이프라인 e2e(qdrant/openai 모킹): 검증 실패 토픽이 저장되지 않고 failed_topics 기록 (에러 삼킴 회귀 방지)
6. import: 성공/rollback/abort
7. admin 인증 401/200

기존 `test_enrichment.py`(26개)는 무변경.

## 10. 구현 순서 (커밋 단위 — 각 단계 후 시스템 정상 동작)

1. **alembic 도입**: 0001_baseline + `main.py` create_all 제거 + stamp 절차 문서화 (동작 무변화)
2. **신규 모델 + 0002 + schemas + crud_lessons** + conftest + 모델/CRUD 테스트 (테이블만 생성, 미사용)
3. **신규 조회 API(`/lessons`) 추가** (구 파일 API와 공존) + **import 스크립트 작성·실행**으로 48개 적재
4. **파이프라인 DB 전환 + admin API 개편** + openai_service 검증 + 구 백업 엔드포인트 제거(현재 프론트에서 이미 401로 불능이라 무해) + 웹훅 수정 + 테스트
5. **프론트 전환** (axios.ts / lessonApi.ts / ReactLearnPage / AdminPanel + admin 키 UI)
6. **정리**: 구 `/lesson/*` 엔드포인트·CONTENT_DIR, StaticFiles 마운트, `migrate_backup_to_datefolders.py` 삭제, 문서 갱신 (ARCHITECTURE.md, README.md, PROCESS_AND_RUN.md, swagger_test_guide.md)

> 순서 근거: 3단계까지는 파일 API 무손상이라 언제든 롤백 가능. 프론트 전환(5) 후에야 구 API 제거(6) → 모든 커밋 시점에 프론트-백엔드 호환 유지.

## 11. 주요 파일

- **백엔드**: `app/models/models.py`, `app/schemas/schemas.py`, `app/crud/crud_lessons.py`(신규), `app/services/content_pipeline_service.py`, `app/services/openai_service.py`, `app/api/lesson_api.py`, `app/api/admin_api.py`, `app/main.py`, `app/scripts/import_lessons_from_files.py`(신규), `alembic/`(신규), `tests/conftest.py`(신규)
- **프론트**: `src/api/axios.ts`, `src/api/lessonApi.ts`, `src/pages/ReactLearnPage.tsx`, `src/pages/AdminPanel.tsx`

## 12. 검증 방법

1. 각 단계마다 `uv run pytest` (기존 26개 + 신규 전부 통과)
2. 3단계 후: import 실행 → `GET /api/v1/lessons`가 초급22·중급14·고급12 반환, 상세 1건을 원본 JSON과 필드 대조
3. 4단계 후: Swagger에서 admin 키로 generate 트리거 → generations 상태 추적, 완료 후 is_current 전환 확인. restore/activate 동작 확인
4. 5단계 후: 프론트 dev 서버로 학습 페이지 목록/상세 렌더링 + AdminPanel 키 입력 후 생성/버전 복원 e2e
5. **유의**: 실행 중인 uvicorn이 이 워크스페이스 복사본인지 먼저 확인 (과거 다른 복사본이 돌던 정황 있음) — 이관·검증은 반드시 이 저장소 기준으로 실행

## 13. 사전 조건

- 시작 전 미커밋 변경 3건 커밋 (index_data.py fix / tasks.md docs / swagger 문서 — 메시지는 이전 논의에서 확정)
- `.env`의 `DATABASE_URL` 대상 PostgreSQL 기동 중 (`docker compose up -d`)
- PostgreSQL 정기 백업(pg_dump) 절차 마련 — 이관 후 `docker compose down -v` 시 레슨 전체가 소실됨 (재생성 = OpenAI 비용)
