# LearnSphere API — 아키텍처 및 코드 문서

> React 학습 플랫폼의 백엔드 API 서버.
> Qdrant(벡터 DB)에 인덱싱된 React 공식 문서를 컨텍스트로 삼아 OpenAI LLM으로 한국어 학습 콘텐츠(레슨)를 자동 생성하고, 이를 **PostgreSQL(세대/버전 모델)**로 관리·제공하며, 같은 문서를 근거로 **RAG 튜터 챗**을 제공하는 FastAPI 애플리케이션입니다.
>
> - (2026-07-24) 레슨 저장소가 `generated_content/` 파일에서 PostgreSQL로 이관 — 근거는 [DB_MIGRATION_PLAN.md](./DB_MIGRATION_PLAN.md)
> - (2026-07-27) AI 튜터 챗봇(Phase 1~12 / M1) 완료 — 학습자 인증(JWT), 대화 영속화, SSE 스트리밍 추가. 기획은 [../chat_bot_plan.md](../chat_bot_plan.md), Phase 계획은 [../chat_bot_detail.md](../chat_bot_detail.md)
>
> **이 문서는 레퍼런스입니다.** 코드를 처음 읽는다면 설계 의도를 설명하는 [CODE_GUIDE.md](./CODE_GUIDE.md)부터 보세요.

---

## 1. 기술 스택

| 구분 | 기술 | 용도 |
|---|---|---|
| 웹 프레임워크 | FastAPI + Uvicorn | REST API 서버 |
| 관계형 DB | PostgreSQL (SQLAlchemy 2.0, psycopg2, alembic) | 레슨 본문(세대/버전), 유저·대화, 콘텐츠 메타데이터 |
| 벡터 DB | Qdrant (qdrant-client) | React 문서 임베딩 저장·검색 |
| LLM | OpenAI API (`gpt-4o-mini`, 환경 변수 `CHAT_MODEL`) | 레슨 JSON 생성 + 튜터 챗 |
| 임베딩 | OpenAI API (`text-embedding-3-small`, 1536차원) | 인덱싱·검색 공용 |
| 에이전트 | LangGraph 1.x + LangChain Core 1.x | 튜터 그래프 (retrieve → generate) |
| 인증 | PyJWT (HS256) + bcrypt | 학습자 로그인 (passlib 미사용 — bcrypt 4.x 호환 이슈) |
| 테스트 | pytest + 인메모리 SQLite | 132개 |
| 설정 | python-dotenv | `.env` 환경 변수 로드 |

> 의존성은 [uv](https://docs.astral.sh/uv/)로 관리합니다. 직접 의존성은 `pyproject.toml`, 전체 버전 고정은 `uv.lock`에 기록됩니다.
>
> **임베딩 전환 주의**: 과거에는 sentence-transformers(`distiluse-base-multilingual-cased-v1`, 384/512차원)를 썼습니다. OpenAI 임베딩(1536차원)으로 바꾸면서 컬렉션이 호환되지 않아 새 컬렉션 `react-docs-openai`를 만들었습니다. 구 컬렉션 `react-docs-complete`는 롤백 대비로 Qdrant에 남아 있습니다.

## 2. 디렉토리 구조

```
learnsphere-api/
├── app/                          # 메인 FastAPI 애플리케이션 패키지
│   ├── main.py                   # 앱 진입점 (라우터 등록, CORS, 웹훅)
│   ├── api/
│   │   ├── lesson_api.py         # 레슨 조회 API (공개, ID 기반)
│   │   ├── admin_api.py          # 콘텐츠 생성·세대/버전 관리 API (관리자 키 인증)
│   │   ├── auth_api.py           # 학습자 가입·로그인·내 정보 (공개)
│   │   └── chat_api.py           # 튜터 챗 세션/메시지/SSE 스트림 (JWT 인증)
│   ├── agents/
│   │   └── tutor_agent.py        # LangGraph RAG 튜터 (retrieve → generate)
│   ├── core/
│   │   ├── database.py           # SQLAlchemy 엔진/세션/Base + session_scope
│   │   ├── security.py           # 관리자 API 키 인증 의존성
│   │   ├── auth.py               # 학습자 인증 (bcrypt 해시 + JWT + get_current_user)
│   │   └── taxonomy.py           # 레벨 ↔ sub_category 매핑
│   ├── crud/
│   │   ├── crud_content.py       # 콘텐츠 메타데이터 조회 쿼리
│   │   ├── crud_lessons.py       # 레슨 세대/버전 CRUD (원자 전환·복원·activate)
│   │   ├── crud_users.py         # 유저 조회·생성
│   │   └── crud_chat.py          # 대화 세션·메시지 (소유권 확인 포함)
│   ├── models/
│   │   └── models.py             # SQLAlchemy ORM 모델 (8개 테이블)
│   ├── schemas/
│   │   ├── schemas.py            # 레슨 스키마 (본문 검증 포함)
│   │   ├── auth.py               # 가입·로그인·토큰·유저 응답
│   │   └── chat.py               # 세션·메시지·챗 응답
│   ├── services/
│   │   ├── content_pipeline_service.py  # 콘텐츠 생성 파이프라인 (DB 세대 단위)
│   │   ├── openai_service.py            # OpenAI 호출 (레슨 생성 + 스키마 검증)
│   │   ├── embedding_service.py         # OpenAI 임베딩 (토큰 계산·배치 분할)
│   │   └── qdrant_service.py            # Qdrant 검색 (레벨 전량 scroll + 유사도 search)
│   └── scripts/
│       ├── seed.py                          # PostgreSQL 초기 데이터 주입
│       ├── import_lessons_from_files.py     # (일회성) 레슨 JSON 파일 → DB 이관
│       └── enrichment/                      # 가공 파이프라인 (별도 문서 참고)
├── alembic/                      # DB 스키마 마이그레이션 (versions/0001~0004)
├── tests/                        # pytest 132개
├── CODE_GUIDE.md                 # 코드 학습 가이드 (설계 의도 중심)
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
    A[react_complete_learning_data.json<br/>React 문서 원본] -->|index_data.py<br/>청킹 + OpenAI 임베딩| B[(Qdrant<br/>react-docs-openai)]
    A -->|scripts/seed.py| C[(PostgreSQL<br/>subjects / learning_content)]

    D[관리자: POST /admin/generate-all-content<br/>또는 웹훅 /webhooks/content-updated] -->|세대 생성 + BackgroundTasks| E[content_pipeline_service]
    B -->|레벨별 토픽 컨텍스트 조회<br/>qdrant_service| E
    E -->|토픽별 프롬프트 전송<br/>openai_service gpt-4o-mini| F[OpenAI API]
    F -->|레슨 JSON + 스키마 검증| E
    E -->|버전 적재 후 finalize<br/>단일 트랜잭션 전환| G[(lessons /<br/>lesson_versions)]

    G -->|GET /lessons, /lessons/id| I[프론트엔드<br/>localhost:5173 / 3000]
    C -->|GET /contents/과목명| I

    I -->|POST /chat/sessions/id/stream<br/>Bearer JWT| J[tutor_agent<br/>LangGraph]
    B -->|질문 임베딩 유사도 top-4<br/>search_similar| J
    G -.->|세션에 lesson_id가 있으면<br/>레슨 본문 주입| J
    J -->|SSE 토큰 스트림| I
    J -->|질문·답변 저장| K[(chat_sessions /<br/>chat_messages)]
```

> 같은 Qdrant 컬렉션을 두 축이 다른 방식으로 씁니다 — 생성은 `scroll`(레벨 전량), 챗은 `query_points`(유사도 top-k).

1. **인덱싱(사전 준비)**: `index_data.py`가 React 문서를 `##` 소제목 단위로 청킹하고 임베딩하여 Qdrant에 업로드. `seed.py`가 같은 데이터의 메타데이터를 PostgreSQL에 주입.
2. **생성(관리자 트리거)**: 관리자 API 또는 웹훅 호출 → `lesson_generations`에 세대(running) 생성 → 백그라운드 파이프라인이 레벨(초급/중급/고급)별로 Qdrant에서 토픽·컨텍스트 수집 → 토픽마다 OpenAI로 레슨 JSON 생성·검증 → `lesson_versions`에 **비활성(is_current=False) 버전으로 적재** → 전 레벨 완료 시 `finalize_generation`이 단일 트랜잭션으로 활성 전환. 진행 중에도 사용자는 이전 세대를 그대로 조회하며, 실패 토픽은 이전 버전 유지 + `failed_topics` 기록(부분 성공 허용).
3. **제공(학습자)**: 프론트엔드가 `GET /lessons`로 레벨별 목차를 받고 `GET /lessons/{id}`로 활성 버전 본문을 조회.
4. **대화(학습자)**: 로그인 후 `POST /chat/sessions`로 세션을 만들고 `.../stream`으로 질문 → 서버가 DB에서 이력을 로드하고 Qdrant에서 근거 문서를 검색해 LangGraph 튜터가 답변을 토큰 단위로 스트리밍 → 질문·답변이 `chat_messages`에 저장. 세션에 `lesson_id`가 있으면 해당 레슨 본문이 검색 문서보다 앞선 근거로 주입됨.

## 4. 데이터베이스 모델 (`app/models/models.py`)

테이블 8개가 세 무리로 나뉩니다.

| 무리 | 테이블 |
|---|---|
| 레슨 콘텐츠 | `lesson_generations`, `lessons`, `lesson_versions` |
| 유저·대화 | `users`, `chat_sessions`, `chat_messages` |
| 메타데이터/유산 | `subjects`, `learning_content`, `lesson_backups`(DEPRECATED) |

### users — 학습자 계정
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | Integer PK | |
| email | String(255), unique, index, not null | 로그인 ID |
| password_hash | String(255), not null | bcrypt 해시 |
| nickname | String(50), not null | 헤더 표시명 |
| created_at | DateTime | |

> `role` 컬럼이 없습니다. 관리자는 계정이 아니라 공유 API 키 체계(`X-Admin-API-Key`)를 쓰므로 두 인증은 별개 경로입니다.

### chat_sessions — 튜터와의 대화 한 묶음
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | Integer PK | |
| user_id | FK → users, index, not null | 소유자 |
| title | String(255), nullable | 첫 질문 앞 40자로 자동 생성 |
| lesson_id | FK → lessons, nullable | 있으면 레슨 사이드패널에서 시작된 대화 |
| created_at / updated_at | DateTime | `updated_at`은 onupdate |

### chat_messages — 대화 한 줄
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | Integer PK | |
| session_id | FK → chat_sessions, index, not null | `cascade="all, delete-orphan"` |
| role | String(20) | `user` / `assistant` |
| content | Text, not null | |
| sources | JSON, nullable | 답변 근거 문서 제목 (assistant만) |
| created_at | DateTime | |

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

| 리비전 | 내용 |
|---|---|
| 0001 | baseline (subjects, learning_content, lesson_backups) |
| 0002 | 레슨 콘텐츠 테이블 (lesson_generations, lessons, lesson_versions) |
| 0003 | users |
| 0004 | chat_sessions, chat_messages |

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

### Auth (학습자 인증) — `auth_api.py`

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/v1/auth/signup` | `{email, password, nickname}` → `{access_token, token_type}`. 이메일 중복 409, 형식 오류 422 |
| POST | `/api/v1/auth/login` | `{email, password}` → `{access_token, token_type}`. 자격증명 불일치 401 |
| GET | `/api/v1/auth/me` | Bearer 토큰으로 내 정보 조회. 토큰 없음/만료/위조 시 401 |

> 토큰은 HS256, 기본 유효기간 7일(`JWT_EXPIRE_MINUTES`). `JWT_SECRET_KEY` 미설정 시 503.

### Chat (튜터 챗) — `chat_api.py`

> 이 라우터 전체가 `Authorization: Bearer <JWT>`를 요구합니다. 남의 세션 접근은 **403**.
> 대화 이력은 요청 본문이 아니라 **DB에서 로드**하므로, 클라이언트가 과거 대화를 들고 다니지 않습니다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/v1/chat/sessions` | Body: `{lesson_id?}`. 세션 생성 → `SessionOut`. 없는 레슨이면 404 |
| GET | `/api/v1/chat/sessions` | 본인 세션 목록 (최근 갱신순) |
| GET | `/api/v1/chat/sessions/{id}/messages` | 세션의 메시지 목록 |
| DELETE | `/api/v1/chat/sessions/{id}` | 세션 삭제 (메시지 cascade) → 204 |
| POST | `/api/v1/chat/sessions/{id}/messages` | 질문 전송 → `{answer, sources}`. 빈 메시지 422, 생성 실패 502 |
| POST | `/api/v1/chat/sessions/{id}/stream` | 질문 전송 (SSE). `text/event-stream` |

**SSE 이벤트 3종** (`POST .../stream`):

```
data: {"type":"token","content":"..."}     답변 조각 (N회)
data: {"type":"done","sources":[...]}      정상 종료
data: {"type":"error","detail":"..."}      생성 실패 (연결은 정상 종료)
```

- 사용자 메시지는 **스트림 시작 전**에 저장됩니다 (클라이언트가 즉시 끊어도 질문은 남음).
- 답변은 제너레이터 `finally`에서 저장되므로, **중도 이탈해도 받은 만큼 저장**됩니다.
- 비스트리밍 `POST .../messages`는 폴백으로 유지됩니다.

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

> 레슨 조회(Lesson, Contents)와 가입·로그인은 인증 없이 공개되어 있습니다. 튜터 챗만 로그인이 필요합니다.

### 인증 체계 요약

| 체계 | 헤더 | 적용 대상 | 미설정 시 |
|---|---|---|---|
| 관리자 | `X-Admin-API-Key` | `/admin/*`, `/webhooks/*` | 503 (`ADMIN_API_KEY` 없음) |
| 학습자 | `Authorization: Bearer` | `/chat/*`, `/auth/me` | 503 (`JWT_SECRET_KEY` 없음) |

## 6. 콘텐츠 생성 파이프라인 상세 (`services/`)

### 6.1 `qdrant_service.get_contexts_by_level(level)`
- 컬렉션(`QDRANT_COLLECTION`, 코드 기본값 `react-docs-complete` — **`.env`에서 `react-docs-openai`로 지정**)에서 `sub_category` 서버 사이드 필터 + 페이지네이션 **scroll**로 해당 레벨 문서만 전량 조회 (벡터 검색 아님).
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

## 6.5 튜터 챗 (RAG) 상세

### 6.5.1 `embedding_service`
- 모델 `text-embedding-3-small`(1536차원). 인덱싱(`index_data.py`)과 검색(`search_similar`)이 공유합니다.
- **입력당 8000토큰** 상한(API 한도 8192에서 여유). 넘으면 `split_text_by_tokens()`로 문단 경계 우선 분할.
- **요청당 100개 / 250,000토큰** 상한으로 배치 분할. 개수만 제한하면 긴 청크가 몰릴 때 요청 토큰 한도에 걸리기 때문입니다.
- 클라이언트·인코딩 모두 지연 생성 — import 시점에 API 키를 요구하지 않습니다.

### 6.5.2 `qdrant_service.search_similar(query, top_k, level)`
- 질문을 임베딩해 `query_points()`로 유사도 검색. `get_contexts_by_level`의 scroll 방식과 목적이 다릅니다.
- 반환 `[{text, title, source, score}]` (점수 내림차순).
- **검색 실패를 삼킵니다** — 예외를 빈 리스트로 축약해 Qdrant가 죽어도 챗은 일반 지식으로 답합니다. (레슨 생성 쪽이 실패를 예외로 올리는 것과 대비)

### 6.5.3 `agents/tutor_agent.py` — LangGraph 그래프
```
START → retrieve → generate → END
```
- **State**: `question`, `history`, `lesson_context`, `retrieved`, `answer` (TypedDict)
- **retrieve**: `search_similar(question, top_k=4)` → `retrieved`
- **generate**: 시스템 프롬프트 + 참고 문서 + 최근 대화 + 질문 → `ChatOpenAI` 호출
- **checkpointer 미사용** — 이력은 DB가 주인이고 호출자가 주입합니다.
- 프롬프트 조립 순서: **레슨 본문 → 검색 문서** (학습자가 보는 레슨이 우선 근거)
- 이력은 `MAX_HISTORY_TURNS = 10`으로 절단 (토큰 비용·지연 억제)
- 실패는 `TutorError`로 감싸 API 레이어가 502(비스트리밍) 또는 `error` 이벤트(스트리밍)로 변환

**진입점 2개**
| 함수 | 형태 | 쓰는 곳 |
|---|---|---|
| `run_tutor(...)` | 동기, `(answer, sources)` 반환 | `POST .../messages` |
| `astream_tutor(...)` | async generator, `{"type":"token"\|"sources"}` yield | `POST .../stream` |

> LangGraph의 이벤트 이름·구조는 버전에 따라 바뀝니다. `astream_events(version="v2")` 의존을 `astream_tutor` **한 함수에 격리**해, 라이브러리가 바뀌어도 API 레이어는 손대지 않도록 했습니다.

### 6.5.4 DB 세션 수명 주의
`Depends(get_db)`가 준 세션은 응답 본문이 끝나기 전에 닫힐 수 있습니다. 요청보다 오래 사는 작업은 세션을 따로 얻습니다.

| 방법 | 언제 |
|---|---|
| `Depends(get_db)` | 보통의 요청 |
| `SessionLocal()` 직접 | BackgroundTask (파이프라인) |
| `session_scope()` (의존성 `get_session_scope`) | 스트리밍 응답 제너레이터 |

`session_scope`를 의존성으로 노출한 이유는 테스트에서 갈아끼우기 위해서입니다 (`tests/conftest.py`).

## 7. 독립 실행 스크립트

| 파일 | 실행 위치 | 역할 |
|---|---|---|
| `index_data.py` | 루트 | `react_complete_learning_data.json`을 `##` 단위로 청킹, 메타데이터를 텍스트에 포함해 **OpenAI 임베딩**(1536차원) 후 Qdrant 컬렉션(`QDRANT_COLLECTION`)에 업로드. `recreate_collection` — **해당 컬렉션 삭제 후 재생성**이므로 컬렉션 이름을 반드시 확인할 것. OpenAI 비용 발생 |
| `app/scripts/seed.py` | 루트에서 모듈 실행 | 'React' Subject 생성 + 학습 콘텐츠 메타데이터를 PostgreSQL에 주입 (`source_path` 기준 중복 방지) |
| `app/scripts/import_lessons_from_files.py` | 루트에서 모듈 실행 | (일회성) 구 `generated_content/` 레슨 JSON을 DB(lessons/lesson_versions)로 이관. `--content-dir` 필수, all-or-nothing, 비어있지 않으면 `--force` 필요 — 2026-07-24 48개 이관 완료 |
| `validated_json_server.py` | 루트 | **별도 서버(포트 8001)**. `validated_lessons_json/` 폴더의 검증된 레슨을 5분 인메모리 캐시와 함께 제공. 메인 앱과 무관하게 단독 실행 (`python validated_json_server.py`) |

> `react_complete_learning_data.json`(141개 문서, 6필드)은 가공 파이프라인(`app/scripts/enrichment/`, `uv run python -m app.scripts.enrich_learning_data`)이 raw(`react_docs_data.json`)로부터 재생성하며 저장소에 커밋되어 있습니다. 인덱싱(571 청크)·시딩(141행)은 2026-07-24 실행 완료 상태입니다.

## 8. 환경 변수 및 실행 방법

`.env` (예시: `ENV_EXAMPLE.txt`):

```env
DATABASE_URL=postgresql://user:password@localhost:5432/learnsphere_db
QDRANT_URL=http://localhost:6333        # 또는 Qdrant Cloud URL
QDRANT_API_KEY=your-qdrant-api-key
QDRANT_COLLECTION=react-docs-openai     # 인덱싱·파이프라인·챗 공용 컬렉션 (OpenAI 임베딩 1536차원)
OPENAI_API_KEY=your-openai-api-key
CHAT_MODEL=gpt-4o-mini                  # 튜터 챗 모델 (선택, 기본값 동일)
EMBEDDING_MODEL=text-embedding-3-small  # 인덱싱·검색 공용 (선택, 기본값 동일)
ADMIN_API_KEY=your-admin-api-key        # 관리자 API/웹훅 인증 키 (필수 — 미설정 시 관리자 기능 503)
JWT_SECRET_KEY=...                      # 학습자 로그인 서명 키. HS256이므로 32바이트 이상
                                        # (필수 — 미설정 시 챗/인증 503)
JWT_EXPIRE_MINUTES=10080                # 토큰 유효기간(분). 선택, 기본 7일
```

> `JWT_SECRET_KEY` 생성: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

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

### 추가 완료 (2026-07-27) — AI 튜터 챗봇 (Phase 1~12 / M1)

- **학습자 인증 도입**: `users` 테이블 + bcrypt 해시 + JWT(HS256). 관리자 키 체계와 별개 경로로 공존 (`core/auth.py`, alembic 0003).
- **RAG 튜터**: LangGraph 2노드 그래프(retrieve → generate). 우리 React 문서를 근거로 답하고 출처를 표시. 레슨 사이드패널에서는 해당 레슨 본문을 우선 근거로 주입.
- **임베딩 전환**: sentence-transformers → OpenAI `text-embedding-3-small`. 서빙 프로세스가 수백 MB 모델을 로드하던 부담 제거. 신규 컬렉션 `react-docs-openai`(1536차원, 862포인트) 생성, 구 컬렉션은 롤백 대비 보존.
- **대화 영속화**: `chat_sessions` / `chat_messages` (alembic 0004). 이력을 요청 본문이 아닌 **DB에서 로드**해 주입.
- **SSE 스트리밍**: `POST /chat/sessions/{id}/stream`. 사용자 메시지는 스트림 시작 전 저장, 답변은 `finally`에서 저장해 **중도 이탈에도 보존**.
- **세션 수명 분리**: `core/database.py`에 `session_scope()` / `get_session_scope()` 추가 — 스트리밍 응답이 요청 세션보다 오래 사는 문제 해결.
- **테스트 확대**: 60개 → **132개** (챗 26, 튜터 에이전트 12, 인증 9, 임베딩·검색 등).

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
