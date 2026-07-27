# LearnSphere API — 아키텍처 및 코드 문서

> React 학습 플랫폼의 백엔드 API 서버.
> Qdrant(벡터 DB)에 인덱싱된 React 공식 문서를 컨텍스트로 삼아 OpenAI LLM으로 한국어 학습 콘텐츠(레슨)를 자동 생성하고, 이를 **PostgreSQL(세대/버전 모델)**로 관리·제공하는 FastAPI 애플리케이션입니다.
>
> (2026-07-24) 레슨 저장소가 `generated_content/` 파일에서 PostgreSQL로 이관되었습니다 — 설계 근거는 [DB_MIGRATION_PLAN.md](./DB_MIGRATION_PLAN.md) 참고.

---

## 1. 기술 스택

| 구분 | 기술 | 용도 |
|---|---|---|
| 웹 프레임워크 | FastAPI 0.116 + Uvicorn | REST API 서버 |
| 관계형 DB | PostgreSQL (SQLAlchemy 2.0, psycopg2, alembic) | 레슨 본문(세대/버전), 콘텐츠 메타데이터 |
| 벡터 DB | Qdrant (qdrant-client 1.14) | React 문서 임베딩 저장·검색 |
| LLM | OpenAI API (`gpt-4o-mini`) | 학습 자료(레슨) JSON 생성 |
| 임베딩 | sentence-transformers (`distiluse-base-multilingual-cased-v1`) | 문서 인덱싱 시 벡터화 |
| 설정 | python-dotenv | `.env` 환경 변수 로드 |

> 의존성은 [uv](https://docs.astral.sh/uv/)로 관리합니다. 직접 의존성은 `pyproject.toml`, 전체 버전 고정은 `uv.lock`에 기록됩니다.

## 2. 디렉토리 구조

```
learnsphere-api/
├── app/                          # 메인 FastAPI 애플리케이션 패키지
│   ├── main.py                   # 앱 진입점 (라우터 등록, CORS, 웹훅)
│   ├── api/
│   │   ├── lesson_api.py         # 레슨 조회 API (학습자용, ID 기반)
│   │   └── admin_api.py          # 콘텐츠 생성·세대/버전 관리 API (관리자용, API 키 인증)
│   ├── core/
│   │   ├── database.py           # SQLAlchemy 엔진/세션/Base 설정
│   │   └── security.py           # 관리자 API 키 인증 의존성
│   ├── crud/
│   │   ├── crud_content.py       # 콘텐츠 메타데이터 조회 쿼리
│   │   └── crud_lessons.py       # 레슨 세대/버전 CRUD (원자 전환·복원·activate)
│   ├── models/
│   │   └── models.py             # SQLAlchemy ORM 모델 (6개 테이블)
│   ├── schemas/
│   │   └── schemas.py            # Pydantic 스키마 (레슨 본문 검증 포함)
│   ├── services/
│   │   ├── content_pipeline_service.py  # 콘텐츠 생성 파이프라인 (DB 세대 단위)
│   │   ├── openai_service.py            # OpenAI 호출 (레슨 생성 + 스키마 검증)
│   │   └── qdrant_service.py            # Qdrant 컨텍스트 검색
│   └── scripts/
│       ├── seed.py                          # PostgreSQL 초기 데이터 주입
│       ├── import_lessons_from_files.py     # (일회성) 레슨 JSON 파일 → DB 이관
│       └── enrichment/                      # 가공 파이프라인 (별도 문서 참고)
├── alembic/                      # DB 스키마 마이그레이션 (versions/0001, 0002)
├── tests/                        # pytest (가공 파이프라인 + 레슨 DB 60개)
├── index_data.py                 # React 문서 → Qdrant 인덱싱 스크립트 (독립 실행)
├── validated_json_server.py      # 검증된 레슨 전용 별도 서버 (포트 8001, 독립 실행)
├── react_docs_data.json          # React 문서 원본 데이터
├── pyproject.toml                # 직접 의존성 정의 (uv)
├── uv.lock                       # 전체 의존성 버전 고정 (uv)
├── ENV_EXAMPLE.txt               # .env 예시
├── PROCESS_AND_RUN.md            # 실행 방법 안내
└── README.md
```

> 과거 레슨 저장소였던 `../generated_content/`(파일 48개 + backup/)는 DB 이관 후 **아카이브로만 보존**되며 코드에서 참조하지 않습니다.

## 3. 전체 데이터 흐름

```mermaid
flowchart TD
    A[react_complete_learning_data.json<br/>React 문서 원본] -->|index_data.py<br/>청킹 + 임베딩| B[(Qdrant<br/>벡터 DB)]
    A -->|scripts/seed.py| C[(PostgreSQL<br/>subjects / learning_content)]

    D[관리자: POST /admin/generate-all-content<br/>또는 웹훅 /webhooks/content-updated] -->|세대 생성 + BackgroundTasks| E[content_pipeline_service]
    B -->|레벨별 토픽 컨텍스트 조회<br/>qdrant_service| E
    E -->|토픽별 프롬프트 전송<br/>openai_service gpt-4o-mini| F[OpenAI API]
    F -->|레슨 JSON + 스키마 검증| E
    E -->|버전 적재 후 finalize<br/>단일 트랜잭션 전환| G[(lessons /<br/>lesson_versions)]

    G -->|GET /lessons, /lessons/id| I[프론트엔드<br/>localhost:5173 / 3000]
    C -->|GET /contents/과목명| I
```

1. **인덱싱(사전 준비)**: `index_data.py`가 React 문서를 `##` 소제목 단위로 청킹하고 임베딩하여 Qdrant에 업로드. `seed.py`가 같은 데이터의 메타데이터를 PostgreSQL에 주입.
2. **생성(관리자 트리거)**: 관리자 API 또는 웹훅 호출 → `lesson_generations`에 세대(running) 생성 → 백그라운드 파이프라인이 레벨(초급/중급/고급)별로 Qdrant에서 토픽·컨텍스트 수집 → 토픽마다 OpenAI로 레슨 JSON 생성·검증 → `lesson_versions`에 **비활성(is_current=False) 버전으로 적재** → 전 레벨 완료 시 `finalize_generation`이 단일 트랜잭션으로 활성 전환. 진행 중에도 사용자는 이전 세대를 그대로 조회하며, 실패 토픽은 이전 버전 유지 + `failed_topics` 기록(부분 성공 허용).
3. **제공(학습자)**: 프론트엔드가 `GET /lessons`로 레벨별 목차를 받고 `GET /lessons/{id}`로 활성 버전 본문을 조회.

## 4. 데이터베이스 모델 (`app/models/models.py`)

### subjects — 학습 과목
| 컬럼 | 타입 | 설명 |
|---|---|---|
| subject_id | Integer PK | |
| subject_name | String, unique, not null | 예: "React" |
| description | Text | |

### learning_content — 학습 콘텐츠 메타데이터
| 컬럼 | 타입 | 설명 |
|---|---|---|
| content_id | Integer PK | |
| subject_id | FK → subjects | |
| title | String, not null | 문서 제목 |
| main_category | String | 대분류 |
| sub_category | String | 소분류 (레벨 매핑에 사용) |
| topic_group | String, nullable | 토픽 그룹 |
| source_path | String, unique | 원본 문서 경로 (중복 시딩 방지 키) |

### lesson_generations — 레슨 생성 배치(세대)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | Integer PK | |
| source | String(20) | `pipeline` / `import` |
| status | String(20) | `running` / `completed` / `failed` |
| created_by / prompt / params | String / Text / JSON | 트리거 주체·생성 파라미터 |
| started_at / completed_at | DateTime | |
| total_topics / succeeded | Integer | 통계 |
| failed_topics | JSON | `[{level, topic, error}]` — 실패 토픽 목록 |

### lessons — 레슨 정체성 (본문 없음)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | Integer PK | 프론트가 사용하는 레슨 ID |
| level | String(20) | 초급/중급/고급 |
| slug | String(255) | 토픽 정규화 슬러그. **UNIQUE(level, slug)** — 재생성 간 동일 레슨을 잇는 안정 키 |
| topic | String(255) | Qdrant 원본 토픽명 |
| archived_at | DateTime, nullable | 새 세대에 없는 토픽 → 숨김(삭제 아님) |

### lesson_versions — 불변 레슨 본문 (버전 = 세대 × 레슨)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | Integer PK | |
| lesson_id / generation_id | FK | UNIQUE(lesson_id, generation_id) |
| title / position | String / Integer | position = 세대 내 레벨별 순번 (프론트 number) |
| core_concepts | Text | |
| code_examples / quizzes | JSON | 퀴즈는 선택 필드 `explanation` 포함 가능 |
| is_current | Boolean | **partial unique index**(lesson_id WHERE is_current) — 레슨당 활성 버전 1개 보장 |

복원(restore)·세대 전환(activate)은 파일 복사가 아니라 `is_current` 이동이므로 데이터 손실 없이 왕복 가능합니다.

### lesson_backups — [DEPRECATED] 파일 백업 시절 이력
파일 저장소 시절의 백업 로그. 신규 기록은 중단됐고 과거 파일 아카이브와 짝을 이루는 읽기 전용 유산으로 유지됩니다 (drop은 추후 결정).

스키마는 **alembic**으로 관리합니다 — 서버 기동 전 `uv run alembic upgrade head` (기존 create_all 시절 DB는 최초 1회 `alembic stamp 0001` 후 upgrade).

## 5. API 엔드포인트

메인 앱(`app.main:app`, 기본 포트 8000). 라우터 prefix는 `/api/v1`.

### 공통
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | 환영 메시지 |
| GET | `/api/health` | 헬스 체크 (`{"status": "ok"}`) |

### Contents (PostgreSQL 기반)
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/v1/contents/{subject_name}` | 과목명(대소문자 무시)으로 콘텐츠 메타데이터 목록 조회. 응답: `LearningContentBase[]` |

### Lesson (DB 기반, 학습자용) — `lesson_api.py`
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/v1/lessons` | 활성 레슨 목록을 레벨별 그룹으로 반환: `{"초급": [{id, title, number}], ...}` (archived 제외) |
| GET | `/api/v1/lessons/{lesson_id}` | 레슨의 활성 버전 본문. 응답 모델: `LessonDetail` (id, level, title, core_concepts, code_examples, quizzes, version_id, updated_at). 없거나 archived면 404 |

### Admin (관리자용) — `admin_api.py`

> Admin 전체와 Webhook 엔드포인트는 `X-Admin-API-Key` 헤더 인증이 필요합니다 (환경 변수 `ADMIN_API_KEY`와 비교, 미설정 시 503).

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/v1/admin/generate-all-content` | 전체 레벨 콘텐츠 재생성을 백그라운드로 시작. `{message, generation_id}` 반환. running 세대 존재 시 **409** |
| GET | `/api/v1/admin/generations` | 세대 목록 (최신순 — id/source/status/시각/성공·실패 수) |
| GET | `/api/v1/admin/generations/{id}` | 세대 상세 + `failed_topics` |
| POST | `/api/v1/admin/generations/{id}/activate` | 해당 세대의 레슨으로 일괄 전환 (트랜잭션, archived 해제 포함). 빈 세대 400 |
| GET | `/api/v1/admin/lessons/{lesson_id}/versions` | 레슨의 전체 버전 목록 (최신순, is_current 표시) |
| POST | `/api/v1/admin/lessons/{lesson_id}/restore` | Body: `{version_id, restored_by?}`. 해당 버전을 활성으로 전환 |

### Webhooks
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/v1/webhooks/content-updated` | Qdrant 데이터 변경 등 이벤트 수신 → 전체 콘텐츠 재생성 파이프라인을 백그라운드로 실행 (현재는 admin 생성 API와 동일 동작) |

> 학습자용 엔드포인트(Lesson, Contents)는 인증 없이 공개되어 있습니다.

## 6. 콘텐츠 생성 파이프라인 상세 (`services/`)

### 6.1 `qdrant_service.get_contexts_by_level(level)`
- 컬렉션(`QDRANT_COLLECTION`, 기본값 `react-docs-complete`)에서 `sub_category` 서버 사이드 필터 + 페이지네이션 **scroll**로 해당 레벨 문서만 전량 조회 (벡터 검색 아님).
- 레벨 → `sub_category` 매핑:
  - 초급: `"1단계: 사전 준비 ⚙️"`, `"2단계: 메인 학습 코스 (초급) 入门"`
  - 중급: `"3단계: 메인 학습 코스 (중급) 🚀"`
  - 고급: `"4단계: 심화 탐구 🧠"`
- 매칭된 포인트를 `title`별로 그룹화하고 텍스트 조각을 `\n\n---\n\n`로 이어붙여 `{토픽: 컨텍스트}` 딕셔너리 반환.

### 6.2 `openai_service.generate_lesson_with_llm(level, topic, context)`
- 모델: `gpt-4o-mini`, `response_format={"type": "json_object"}`.
- 시스템 프롬프트: "React 강사" 역할, 한국어 출력, 고정 JSON 스키마 강제.
- 요구 분량: 핵심 개념 3~5문단+, 코드 예시 2~3개(각 설명 2~3문장+), 퀴즈 3~5개(각 해설 2문장+).
- 응답 파싱 후 `normalize_lesson()` 보정 → **저장 전 `LessonContentSchema`로 검증**. API 오류·파싱 실패·검증 실패는 모두 `LessonGenerationError`로 raise되어 파이프라인이 실패 토픽으로 집계합니다 (과거의 "에러 메시지를 본문에 담은 폴백 레슨" 저장 문제 제거).

### 6.3 `content_pipeline_service`
- `request_full_generation(db, created_by)`: running 세대가 없으면 새 세대(`lesson_generations`, status='running')를 생성. API/웹훅의 중복 실행 가드(409) 공용 헬퍼.
- `run_full_content_generation(generation_id)`: 초급 → 중급 → 고급 순차 실행 후 `finalize_generation()` 호출. 최상위 예외 시 status='failed' (활성 버전 무변경 — 사용자 영향 없음).
- `run_content_generation_for_level(...)`: 토픽마다
  1. LLM 생성 + 스키마 검증 (실패 시 `failed_topics`에 누적하고 다음 토픽 진행)
  2. `lessons` upsert (키: level + slug) → `lesson_versions`에 **is_current=False**로 적재 + 레슨 단위 커밋
- `finalize_generation()` (crud_lessons): 단일 트랜잭션으로 새 버전 활성 전환, 세대에 없는 레슨 archived 처리, 실패 토픽 레슨은 이전 버전 유지, 세대 통계 기록.

## 7. 독립 실행 스크립트

| 파일 | 실행 위치 | 역할 |
|---|---|---|
| `index_data.py` | 루트 | `react_complete_learning_data.json`을 `##` 단위로 청킹, 메타데이터를 텍스트에 포함해 임베딩 후 Qdrant 컬렉션(`QDRANT_COLLECTION`, 기본값 `react-docs-complete`)에 업로드(recreate — **기존 컬렉션 삭제 후 재생성**) |
| `app/scripts/seed.py` | 루트에서 모듈 실행 | 'React' Subject 생성 + 학습 콘텐츠 메타데이터를 PostgreSQL에 주입 (`source_path` 기준 중복 방지) |
| `app/scripts/import_lessons_from_files.py` | 루트에서 모듈 실행 | (일회성) 구 `generated_content/` 레슨 JSON을 DB(lessons/lesson_versions)로 이관. `--content-dir` 필수, all-or-nothing, 비어있지 않으면 `--force` 필요 — 2026-07-24 48개 이관 완료 |
| `validated_json_server.py` | 루트 | **별도 서버(포트 8001)**. `validated_lessons_json/` 폴더의 검증된 레슨을 5분 인메모리 캐시와 함께 제공. 메인 앱과 무관하게 단독 실행 (`python validated_json_server.py`) |

> `react_complete_learning_data.json`(141개 문서, 6필드)은 가공 파이프라인(`app/scripts/enrichment/`, `uv run python -m app.scripts.enrich_learning_data`)이 raw(`react_docs_data.json`)로부터 재생성하며 저장소에 커밋되어 있습니다. 인덱싱(571 청크)·시딩(141행)은 2026-07-24 실행 완료 상태입니다.

## 8. 환경 변수 및 실행 방법

`.env` (예시: `ENV_EXAMPLE.txt`):

```env
DATABASE_URL=postgresql://user:password@localhost:5432/learnsphere_db
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your-qdrant-api-key
QDRANT_COLLECTION=react-docs-complete   # 인덱싱·파이프라인 공용 컬렉션 이름 (선택, 기본값 동일)
OPENAI_API_KEY=your-openai-api-key
ADMIN_API_KEY=your-admin-api-key        # 관리자 API/웹훅 인증 키 (필수 — 미설정 시 관리자 기능 503)
```

실행 순서:

```bash
# 1. 의존성 설치
uv sync

# 2. .env 작성 (위 참고)

# 3. PostgreSQL 실행 (Docker) — 아래 §8.1 참고
docker compose up -d

# 4. DB 스키마 마이그레이션 (alembic)
uv run alembic upgrade head
# (create_all 시절부터 쓰던 기존 DB는 최초 1회 `uv run alembic stamp 0001` 후 upgrade)

# 5. (선택) 데이터 준비
uv run python index_data.py       # Qdrant 인덱싱
uv run python -m app.scripts.seed # PostgreSQL 시딩

# 6. 메인 서버 실행 (포트 8000)
uv run uvicorn app.main:app --reload
# → http://127.0.0.1:8000/docs 에서 Swagger UI 확인

# 7. (선택) 검증된 레슨 서버 (포트 8001)
uv run python validated_json_server.py
```

CORS 허용 오리진: `localhost:5173`, `localhost:3000` (및 127.0.0.1 대응 — Vite/CRA 프론트엔드용).

### 8.1 PostgreSQL (Docker)

`docker-compose.yml`이 개발용 PostgreSQL 16 컨테이너를 정의합니다. 접속 정보는 `.env`의 `POSTGRES_*` 값(미지정 시 기본값)을 사용하며, 이 값은 `DATABASE_URL`과 일치해야 합니다.

| 항목 | 기본값 | 오버라이드 변수 |
|---|---|---|
| 사용자 | `user` | `POSTGRES_USER` |
| 비밀번호 | `password` | `POSTGRES_PASSWORD` |
| DB 이름 | `learnsphere_db` | `POSTGRES_DB` |
| 호스트 포트 | `5432` | `POSTGRES_PORT` |

```bash
docker compose up -d        # 시작 (백그라운드)
docker compose ps           # 상태 확인 (healthy 확인)
docker compose logs -f db   # 로그
docker compose down         # 중지 (데이터 볼륨 유지)
docker compose down -v      # 중지 + 데이터 볼륨 삭제
```

- 데이터는 명명된 볼륨 `learnsphere_postgres_data`에 영속 저장됩니다.
- 헬스체크(`pg_isready`)로 DB가 실제 접속 가능해질 때까지 `healthy` 상태를 표시하지 않습니다.
- 테이블은 `uv run alembic upgrade head`로 생성합니다 (앱 기동 시 자동 생성 없음). 초기 데이터는 `python -m app.scripts.seed`로 주입합니다.
- **레슨 본문이 이 DB에만 존재하므로** `docker compose down -v`는 레슨 전체를 삭제합니다. 재생성에는 OpenAI 비용이 들므로 `pg_dump` 정기 백업을 권장합니다.
- 기본값(`user`/`password`)은 로컬 개발 전용입니다. 운영 환경에서는 `.env`에서 반드시 강한 값으로 교체하세요.

## 9. 이슈 수정 이력 및 잔여 개선 포인트

### 수정 완료 (2026-07-24) — 레슨 저장소 DB 이관

- **레슨 저장소 이관**: `generated_content/` 파일 → PostgreSQL 세대/버전 모델 (`lesson_generations`/`lessons`/`lesson_versions`). 파일명 파싱 기반 index.json, 비원자적 쓰기, 재생성 중 신구 혼재, 구파일 잔존 문제 해소.
- **alembic 도입**: `create_all()` 제거, baseline(0001) + 신규 테이블(0002) 마이그레이션.
- **에러 삼킴 제거**: LLM 실패가 본문에 담겨 저장되던 문제 → 생성 시점 스키마 검증 + 실패 토픽 집계로 전환.
- **관리자 API 개편**: 파일 백업/복원 4종 → 세대/버전 API 6종. 프론트 `X-Admin-API-Key` 미전송 401 버그 수정 (키 입력 UI + 인터셉터).
- **테스트 도입**: conftest(in-memory SQLite) + 레슨 DB 테스트 34개 (총 60개).

### 수정 완료 (2026-07-19)

- **관리자 인증 추가**: `/admin/*` 전체와 웹훅에 `X-Admin-API-Key` 헤더 인증 적용 (`app/core/security.py`, 환경 변수 `ADMIN_API_KEY`, 타이밍 세이프 비교).
- **경로 순회 차단**: `GET /lesson/{filename}`에 파일명 검증 추가 — 경로 구분자 포함/`.json` 외 확장자/`CONTENT_DIR` 밖 경로는 400 거부. `restore-backup-date`의 `date` 값도 동일하게 검증.
- **Qdrant 컬렉션 이름 통일**: `index_data.py`와 `qdrant_service.py`가 환경 변수 `QDRANT_COLLECTION`(기본값 `react-docs-complete`)을 공유.
- **Qdrant 조회 개선**: `scroll(limit=2000)` 전량 조회 → `sub_category` 서버 사이드 필터(MatchAny) + 페이지네이션 루프. 문서 수 제한 없이 해당 레벨만 조회.
- **백업 경로 규칙 통일**: `restore-lesson-backup`의 복원 전 백업도 날짜 폴더(`backup/YYYY-MM-DD/`)에 저장하고 DB에 `날짜/파일명` 상대 경로로 기록. 백업 파일 부재 시 404 반환.
- **일괄 복원 파일명 버그 수정**: `restore-backup-date`가 타임스탬프 접미사(`_YYYYMMDD_HHMMSS`, `_restore_...`)를 제거하고 원본 레슨 파일명으로 덮어쓰도록 수정 (기존에는 타임스탬프가 붙은 새 파일이 생성되어 실제 복원이 되지 않았음).
- **LLM 응답 스키마 보정**: `openai_service.normalize_lesson()`이 필수 키를 기본값으로 채워 `LessonContent` 응답 모델과의 불일치로 인한 500 에러 방지.
- **datetime 통일**: 모델 기본값을 `datetime.utcnow` → `datetime.now`로 변경해 파이프라인·백업 폴더명(로컬 시간)과 일치.
- **정리**: `backup-list`의 디버그 `print` 제거, 미사용 파일 `generator_api.py` 삭제.

### 잔여 개선 포인트

- **로깅**: `print` 기반 로깅을 `logging` 모듈로 전환 권장.
- **DB 백업 운영**: 레슨 본문이 DB 단일 저장소가 되었으므로 `pg_dump` 정기 백업 절차 마련 필요.
- **lesson_backups 정리**: deprecated 테이블 drop 시점 결정 (파일 아카이브 보존 정책과 함께).
