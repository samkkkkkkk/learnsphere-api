# LearnSphere API — 아키텍처 및 코드 문서

> React 학습 플랫폼의 백엔드 API 서버.
> Qdrant(벡터 DB)에 인덱싱된 React 공식 문서를 컨텍스트로 삼아 OpenAI LLM으로 한국어 학습 콘텐츠(레슨)를 자동 생성하고, 이를 JSON 파일 + PostgreSQL로 관리·제공하는 FastAPI 애플리케이션입니다.

---

## 1. 기술 스택

| 구분 | 기술 | 용도 |
|---|---|---|
| 웹 프레임워크 | FastAPI 0.116 + Uvicorn | REST API 서버 |
| 관계형 DB | PostgreSQL (SQLAlchemy 2.0, psycopg2) | 콘텐츠 메타데이터, 백업 이력 |
| 벡터 DB | Qdrant (qdrant-client 1.14) | React 문서 임베딩 저장·검색 |
| LLM | OpenAI API (`gpt-4o-mini`) | 학습 자료(레슨) JSON 생성 |
| 임베딩 | sentence-transformers (`distiluse-base-multilingual-cased-v1`) | 문서 인덱싱 시 벡터화 |
| 설정 | python-dotenv | `.env` 환경 변수 로드 |

> 의존성은 [uv](https://docs.astral.sh/uv/)로 관리합니다. 직접 의존성은 `pyproject.toml`, 전체 버전 고정은 `uv.lock`에 기록됩니다.

## 2. 디렉토리 구조

```
learnsphere-api/
├── app/                          # 메인 FastAPI 애플리케이션 패키지
│   ├── main.py                   # 앱 진입점 (라우터 등록, CORS, 정적 파일)
│   ├── api/
│   │   ├── lesson_api.py         # 레슨 조회 API (학습자용)
│   │   └── admin_api.py          # 콘텐츠 생성·백업·복원 API (관리자용, API 키 인증)
│   ├── core/
│   │   ├── database.py           # SQLAlchemy 엔진/세션/Base 설정
│   │   └── security.py           # 관리자 API 키 인증 의존성
│   ├── crud/
│   │   └── crud_content.py       # 콘텐츠 조회 쿼리
│   ├── models/
│   │   └── models.py             # SQLAlchemy ORM 모델 (3개 테이블)
│   ├── schemas/
│   │   └── schemas.py            # Pydantic 응답 스키마
│   ├── services/
│   │   ├── content_pipeline_service.py  # 콘텐츠 생성 파이프라인 (핵심 로직)
│   │   ├── openai_service.py            # OpenAI 호출 (레슨 생성)
│   │   └── qdrant_service.py            # Qdrant 컨텍스트 검색
│   └── scripts/
│       ├── seed.py                          # PostgreSQL 초기 데이터 주입
│       └── migrate_backup_to_datefolders.py # 백업 파일 날짜별 폴더 마이그레이션
├── index_data.py                 # React 문서 → Qdrant 인덱싱 스크립트 (독립 실행)
├── validated_json_server.py      # 검증된 레슨 전용 별도 서버 (포트 8001, 독립 실행)
├── react_docs_data.json          # React 문서 원본 데이터
├── pyproject.toml                # 직접 의존성 정의 (uv)
├── uv.lock                       # 전체 의존성 버전 고정 (uv)
├── ENV_EXAMPLE.txt               # .env 예시
├── PROCESS_AND_RUN.md            # 실행 방법 안내
└── README.md
```

메인 앱 외부(상위 폴더)에 생성되는 디렉토리:

```
../generated_content/             # LLM이 생성한 레슨 JSON 저장소
├── index.json                    # 레벨별 레슨 목록 인덱스
├── {레벨}_{번호}_{제목}.json      # 개별 레슨 파일 (예: 초급_01_JSX로-마크업-작성하기.json)
└── backup/
    └── YYYY-MM-DD/               # 날짜별 백업 폴더
        └── {레슨명}_{타임스탬프}.json
```

## 3. 전체 데이터 흐름

```mermaid
flowchart TD
    A[react_complete_learning_data.json<br/>React 문서 원본] -->|index_data.py<br/>청킹 + 임베딩| B[(Qdrant<br/>벡터 DB)]
    A -->|scripts/seed.py| C[(PostgreSQL<br/>subjects / learning_content)]

    D[관리자: POST /admin/generate-all-content<br/>또는 웹훅 /webhooks/content-updated] -->|BackgroundTasks| E[content_pipeline_service]
    B -->|레벨별 토픽 컨텍스트 조회<br/>qdrant_service| E
    E -->|토픽별 프롬프트 전송<br/>openai_service gpt-4o-mini| F[OpenAI API]
    F -->|레슨 JSON| E
    E -->|파일 저장 + index.json 생성| G[generated_content/]
    E -->|백업·생성 이력 기록| H[(lesson_backups 테이블)]

    G -->|GET /lesson/index, /lesson/파일명| I[프론트엔드<br/>localhost:5173 / 3000]
    C -->|GET /contents/과목명| I
```

1. **인덱싱(사전 준비)**: `index_data.py`가 React 문서를 `##` 소제목 단위로 청킹하고 임베딩하여 Qdrant에 업로드. `seed.py`가 같은 데이터의 메타데이터를 PostgreSQL에 주입.
2. **생성(관리자 트리거)**: 관리자 API 또는 웹훅 호출 → 백그라운드 태스크로 파이프라인 실행 → 레벨(초급/중급/고급)별로 Qdrant에서 토픽·컨텍스트 수집 → 토픽마다 OpenAI로 레슨 JSON 생성 → 파일 저장(기존 파일은 자동 백업) → `index.json` 갱신.
3. **제공(학습자)**: 프론트엔드가 `index.json`으로 목차를 받고 개별 레슨 파일을 조회.

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

### lesson_backups — 레슨 파일 변경 이력
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | Integer PK | |
| lesson_filename | String(255) | 원본 레슨 파일명 |
| backup_filename | String(255) | 백업 파일 상대 경로 (`YYYY-MM-DD/파일명`) |
| created_at | DateTime | 기본값 UTC now |
| created_by | String(100) | 수행자 |
| prompt | Text | 생성 시 사용한 프롬프트(선택) |
| params | JSON | 생성 파라미터(선택) |
| action | String(50) | `create` / `backup` / `restore` / `backup-before-restore` 등 |

테이블은 `main.py` 기동 시 `Base.metadata.create_all()`로 자동 생성됩니다(마이그레이션 도구 없음).

## 5. API 엔드포인트

메인 앱(`app.main:app`, 기본 포트 8000). 라우터 prefix는 `/api/v1`.

### 공통
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | 환영 메시지 |
| GET | `/api/health` | 헬스 체크 (`{"status": "ok"}`) |
| GET | `/static/content/*` | `generated_content/` 정적 파일 서빙 |

### Contents (PostgreSQL 기반)
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/v1/contents/{subject_name}` | 과목명(대소문자 무시)으로 콘텐츠 메타데이터 목록 조회. 응답: `LearningContentBase[]` |

### Lesson (파일 기반, 학습자용) — `lesson_api.py`
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/v1/lesson/index` | `generated_content/index.json` 반환. 없으면 404 |
| GET | `/api/v1/lesson/{filename}` | 개별 레슨 JSON 반환. 응답 모델: `LessonContent` (title, level, core_concepts, code_examples, quizzes) |

### Admin (관리자용) — `admin_api.py`

> Admin 전체와 Webhook 엔드포인트는 `X-Admin-API-Key` 헤더 인증이 필요합니다 (환경 변수 `ADMIN_API_KEY`와 비교, 미설정 시 503).

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/v1/admin/generate-all-content` | 전체 레벨(초급·중급·고급) 콘텐츠 재생성을 백그라운드로 시작 |
| GET | `/api/v1/admin/lesson-backups?lesson_filename=...` | 특정 레슨의 백업 이력 목록 (DB 조회, 최신순) |
| POST | `/api/v1/admin/restore-lesson-backup` | Body: `{backup_id, restored_by?}`. 백업본으로 레슨 복원. 복원 전 현재 파일도 자동 백업 |
| GET | `/api/v1/admin/backup-list` | `backup/` 하위 날짜 폴더별 백업 파일 목록 (`{"2024-06-08": ["파일.json", ...]}`) |
| POST | `/api/v1/admin/restore-backup-date` | Body: `{date}`. 해당 날짜 폴더의 모든 백업을 `generated_content/` 최상위로 일괄 복원(덮어쓰기) |

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
- 실패 시 예외를 던지지 않고 오류 메시지가 `core_concepts`에 담긴 **폴백 JSON**을 반환 → 파이프라인이 중단되지 않지만 오류 내용이 레슨 파일로 저장될 수 있음.
- 응답 파싱 후 `normalize_lesson()`으로 필수 키(title, level, core_concepts, code_examples, quizzes)를 보정해 응답 모델과의 스키마 불일치를 방지.

### 6.3 `content_pipeline_service`
- `run_full_content_generation()`: 초급 → 중급 → 고급 순차 실행 후 `create_index_file()` 호출.
- `run_content_generation_for_level(level, ...)`: 토픽마다
  1. 파일명 생성: `{레벨}_{순번:02d}_{안전화된-제목}.json`
  2. 동일 파일 존재 시 → `backup/YYYY-MM-DD/{파일명}_{타임스탬프}.json`으로 복사 + `lesson_backups`에 `action='backup'` 기록
  3. 새 레슨 저장 + `action='create'` 기록
- `create_index_file()`: `generated_content/` 내 파일명을 `레벨_번호_제목` 규칙으로 파싱해 `index.json` 생성. **파일명 규칙이 곧 인덱스의 데이터 소스**이므로 파일명 형식이 깨지면 인덱스에서 누락됩니다.

## 7. 독립 실행 스크립트

| 파일 | 실행 위치 | 역할 |
|---|---|---|
| `index_data.py` | 루트 | `react_complete_learning_data.json`을 `##` 단위로 청킹, 메타데이터를 텍스트에 포함해 임베딩 후 Qdrant 컬렉션(`QDRANT_COLLECTION`, 기본값 `react-docs-complete`)에 업로드(recreate — **기존 컬렉션 삭제 후 재생성**) |
| `app/scripts/seed.py` | 루트에서 모듈 실행 | 'React' Subject 생성 + 학습 콘텐츠 메타데이터를 PostgreSQL에 주입 (`source_path` 기준 중복 방지) |
| `app/scripts/migrate_backup_to_datefolders.py` | 루트에서 실행 | 평면 구조였던 백업 파일을 파일명의 타임스탬프 기준 날짜 폴더로 이동 + DB의 `backup_filename` 경로 갱신 (1회성 마이그레이션) |
| `validated_json_server.py` | 루트 | **별도 서버(포트 8001)**. `validated_lessons_json/` 폴더의 검증된 레슨을 5분 인메모리 캐시와 함께 제공. 메인 앱과 무관하게 단독 실행 (`python validated_json_server.py`) |

> ⚠️ 데이터 파일 누락: `index_data.py`/`seed.py`가 참조하는 `react_complete_learning_data.json`은 저장소에 없습니다. 루트의 `react_docs_data.json`은 스키마가 달라(`source`/`content` 필드만 존재, 카테고리·제목 메타데이터 없음) 대체할 수 없으므로, 인덱싱·시딩 실행 전 해당 파일을 준비해야 합니다.

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

# 4. (선택) 데이터 준비
uv run python index_data.py       # Qdrant 인덱싱
uv run python -m app.scripts.seed # PostgreSQL 시딩

# 5. 메인 서버 실행 (포트 8000)
uv run uvicorn app.main:app --reload
# → http://127.0.0.1:8000/docs 에서 Swagger UI 확인

# 6. (선택) 검증된 레슨 서버 (포트 8001)
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
- 테이블은 앱 기동 시 `create_all()`로 자동 생성되므로 별도 초기화 SQL은 필요 없습니다. 초기 데이터는 `python -m app.scripts.seed`로 주입합니다.
- 기본값(`user`/`password`)은 로컬 개발 전용입니다. 운영 환경에서는 `.env`에서 반드시 강한 값으로 교체하세요.

## 9. 이슈 수정 이력 및 잔여 개선 포인트

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

- **데이터 파일 누락**: `react_complete_learning_data.json`이 저장소에 없어 인덱싱(`index_data.py`)·시딩(`seed.py`)을 실행할 수 없음. 루트의 `react_docs_data.json`은 스키마가 달라 대체 불가 (§7 참고).
- **DB 마이그레이션 부재**: 테이블 생성이 `create_all()` 의존 — 스키마 변경 시 Alembic 등 마이그레이션 도구 도입 권장.
- **requirements 정리**: langchain 계열 등 미사용 의존성 다수 포함.
- **로깅**: `print` 기반 로깅을 `logging` 모듈로 전환 권장.
- **테스트 부재**: 자동화된 테스트가 없음.
