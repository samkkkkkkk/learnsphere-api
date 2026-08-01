# LearnSphere API

React 학습 플랫폼 **LearnSphere**의 백엔드 API 서버입니다.

Qdrant(벡터 DB)에 인덱싱된 React 공식 문서를 컨텍스트로 활용해 OpenAI LLM(`gpt-4o-mini`)으로 한국어 학습 콘텐츠(레슨)를 자동 생성하고, 생성된 레슨을 **PostgreSQL(세대/버전 모델)**로 관리·제공하며, 같은 문서를 근거로 **RAG 튜터 챗**을 제공합니다. 여기에 **학습 관리**(목표·일정·진도·AI 피드백)와 **관리자 문서 업로드 인덱싱** 기능을 더해 학습 루프 전반을 지원합니다.

## 주요 기능

- **레슨 자동 생성**: 레벨(초급/중급/고급)별로 Qdrant에서 토픽 컨텍스트를 수집하고, LLM으로 핵심 개념·코드 예시·퀴즈가 포함된 레슨을 생성해 DB에 적재 (백그라운드 실행, 세대 단위 원자 전환 — 진행 중에도 이전 세대 서빙)
- **레슨 제공 API**: 프론트엔드(Vite/CRA)를 위한 레벨별 레슨 목록 및 개별 레슨 조회 (ID 기반)
- **세대/버전 관리**: 재생성마다 불변 버전이 쌓이며, 관리자 API로 버전 단위 복원·세대 단위 전환 지원 (데이터 손실 없는 왕복)
- **AI 튜터 챗 (RAG)**: LangGraph 튜터가 질문을 임베딩해 Qdrant에서 근거 문서를 검색하고 답변 생성. 멀티턴 대화는 DB에 영속화되며, 답변은 SSE로 토큰 단위 스트리밍
- **학습자 인증**: 가입·로그인(bcrypt + JWT HS256). 튜터 챗·학습 관리는 로그인 사용자 전용이며 리소스 소유권을 검사
- **학습 관리**: 학습 목표·일정 CRUD, 진도율 집계 대시보드, 레슨 진도 기록, 로컬 데이터 이관, LLM 기반 AI 학습 피드백 (모두 학습자 소유권 검사)
- **문서 업로드 인덱싱**: 관리자가 문서(pdf/md/txt)를 업로드하면 백그라운드에서 청킹·임베딩 후 별도 Qdrant 컬렉션(`uploaded-docs`)에 색인 (React 문서 컬렉션과 분리, 결정적 `uuid5` ID로 재업로드 시 멱등)
- **웹훅**: 원본 데이터 변경 이벤트 수신 시 콘텐츠 재생성 파이프라인 트리거

## 기술 스택

| 구분 | 기술 |
|---|---|
| 웹 프레임워크 | FastAPI + Uvicorn |
| 관계형 DB | PostgreSQL (SQLAlchemy 2.0, alembic) |
| 벡터 DB | Qdrant |
| LLM | OpenAI API (`gpt-4o-mini`) |
| 임베딩 | OpenAI API (`text-embedding-3-small`, 1536차원) |
| 에이전트 | LangGraph + LangChain Core (RAG 튜터 · AI 피드백) |
| 문서 처리 | pypdf (pdf/md/txt 추출·청킹) |
| 인증 | PyJWT (HS256) + bcrypt |
| 테스트 | pytest (인메모리 SQLite) |

> 의존성은 [uv](https://docs.astral.sh/uv/)로 관리합니다 (`pyproject.toml` + `uv.lock`).

## 빠른 시작

```bash
# 1. 의존성 설치 (uv가 .venv 생성 + uv.lock 기준으로 설치)
uv sync

# 2. 환경 변수 설정 (ENV_EXAMPLE.txt 참고하여 .env 생성)
#    DATABASE_URL, QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION, QDRANT_DOCS_COLLECTION,
#    OPENAI_API_KEY, CHAT_MODEL, EMBEDDING_MODEL, ADMIN_API_KEY, JWT_SECRET_KEY

# 3. PostgreSQL 실행 (Docker)
docker compose up -d              # postgres:16 컨테이너 시작 (healthy까지 대기)

# 4. DB 스키마 마이그레이션 (alembic)
uv run alembic upgrade head       # 신규 DB: 전체 테이블 생성
# (create_all 시절부터 쓰던 기존 DB는 최초 1회 `uv run alembic stamp 0001` 후 upgrade)

# 5. (최초 1회) 데이터 준비
uv run python index_data.py       # React 문서 → OpenAI 임베딩 → Qdrant 인덱싱
uv run python -m app.scripts.seed # 메타데이터 → PostgreSQL 시딩

# 6. 서버 실행 (포트 8000)
uv run uvicorn app.main:app --reload
```

서버 실행 후 http://127.0.0.1:8000/docs 에서 Swagger UI로 API를 확인할 수 있습니다.

테스트는 `uv run pytest`로 실행합니다 (외부 API 없이 인메모리 SQLite로 동작하며, 느린 테스트는 `-m "not slow"`로 제외).

> PostgreSQL은 `docker-compose.yml`로 실행합니다. 접속 정보(`user`/`password`/`learnsphere_db`/포트 5432)는 `.env`의 `POSTGRES_*`로 오버라이드할 수 있으며 `DATABASE_URL`과 일치해야 합니다. 
>
> **임베딩 컬렉션 주의**: OpenAI 임베딩(1536차원)으로 전환하면서 컬렉션을 `react-docs-openai`로 새로 만들었습니다. 구 컬렉션 `react-docs-complete`(sentence-transformers 384차원)는 호환되지 않으므로 `.env`의 `QDRANT_COLLECTION`을 반드시 지정하세요.

## 주요 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/health` | 헬스 체크 |
| GET | `/api/v1/lessons` | 레벨별 레슨 목록 조회 |
| GET | `/api/v1/lessons/{lesson_id}` | 개별 레슨 조회 (활성 버전) |
| GET | `/api/v1/contents/{subject_name}` | 과목별 콘텐츠 메타데이터 조회 |
| POST | `/api/v1/auth/signup` | 학습자 가입 → JWT 발급 |
| POST | `/api/v1/auth/login` | 학습자 로그인 → JWT 발급 |
| GET | `/api/v1/auth/me` | 내 정보 조회 (Bearer 토큰) |
| POST | `/api/v1/chat/sessions` | 튜터 챗 세션 생성 (레슨 연결 가능) |
| GET | `/api/v1/chat/sessions` | 내 세션 목록 조회 |
| GET | `/api/v1/chat/sessions/{id}/messages` | 세션 메시지 목록 조회 |
| POST | `/api/v1/chat/sessions/{id}/stream` | 질문 전송 (SSE 토큰 스트리밍) |
| POST | `/api/v1/chat/sessions/{id}/messages` | 질문 전송 (비스트리밍 폴백) |
| POST · GET · PATCH · DELETE | `/api/v1/learning/goals[/{id}]` | 학습 목표 CRUD (학습자) |
| POST · GET · PATCH · DELETE | `/api/v1/learning/schedules[/{id}]` | 학습 일정 CRUD (학습자) |
| GET | `/api/v1/learning/dashboard` | 진도율·통계 대시보드 (학습자) |
| POST | `/api/v1/learning/feedback` | AI 학습 피드백 생성 (학습자) |
| PUT · GET | `/api/v1/learning/lesson-progress[/{lesson_id}]` | 레슨 진도 기록·조회 (학습자) |
| POST | `/api/v1/learning/lesson-progress/import` · `/api/v1/learning/import` | 로컬 데이터 일괄 이관 (학습자) |
| POST · GET · DELETE | `/api/v1/admin/documents[/{id}]` | [관리자] 문서 업로드(202)·목록·조회·삭제 (RAG 인덱싱) |
| POST | `/api/v1/admin/generate-all-content` | [관리자] 전체 레슨 재생성 (백그라운드, 중복 실행 시 409) |
| GET | `/api/v1/admin/generations` | [관리자] 생성 세대 목록 조회 |
| POST | `/api/v1/admin/generations/{id}/activate` | [관리자] 특정 세대로 일괄 전환 |
| GET | `/api/v1/admin/lessons/{id}/versions` | [관리자] 레슨 버전 목록 조회 |
| POST | `/api/v1/admin/lessons/{id}/restore` | [관리자] 특정 버전으로 복원 |

인증 체계는 두 가지입니다.

| 체계 | 헤더 | 적용 대상 |
|---|---|---|
| 관리자 | `X-Admin-API-Key` (`.env`의 `ADMIN_API_KEY`) | `/admin/*` (문서 업로드 포함), `/webhooks/*` |
| 학습자 | `Authorization: Bearer <JWT>` | `/chat/*`, `/learning/*`, `/auth/me` |

레슨 조회와 가입·로그인은 인증 없이 공개되어 있습니다.

## 문서 업로드 RAG 인덱싱 (관리자용)

pdf/md/txt 문서를 업로드하면 백그라운드에서 청킹 → 임베딩 → Qdrant 인덱싱됩니다. 업로드 문서는 전용 컬렉션(`QDRANT_DOCS_COLLECTION`, 기본 `uploaded-docs`)에 저장되어 기존 React 문서 검색·레슨 생성에는 영향을 주지 않습니다. 모든 엔드포인트는 `X-Admin-API-Key` 헤더가 필요합니다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/v1/admin/documents` | 파일 업로드(multipart `file`) → 202 + document_id. 같은 파일명은 409 |
| GET | `/api/v1/admin/documents` | 업로드 문서 목록 |
| GET | `/api/v1/admin/documents/{id}` | 상태 조회 (pending → processing → completed/failed) |
| DELETE | `/api/v1/admin/documents/{id}` | 문서 삭제 (Qdrant 포인트 + DB 행). 삭제 후 같은 파일명 재업로드 가능 |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/documents \
  -H "X-Admin-API-Key: $ADMIN_API_KEY" -F "file=@guide.md"
```

> **한계**: 파일 크기 상한은 20MB입니다. 서버 재시작 시 pending/processing에 멈춘 문서는 자동 복구되지 않으므로, 삭제 후 재업로드하세요. (업로드 문서는 색인만 되며, 튜터 챗 검색 연동은 로드맵입니다.)

## 프로젝트 구조

```
learnsphere-api/
├── app/
│   ├── main.py           # 앱 진입점 (라우터 등록, CORS, 웹훅)
│   ├── api/              # API 라우터 (lesson, admin, auth, chat, learning, documents)
│   ├── agents/           # LangGraph RAG 튜터(retrieve → generate) · AI 피드백 에이전트
│   ├── core/             # DB 연결, 관리자 키·학습자 JWT 인증, 레벨 매핑
│   ├── crud/             # DB 조회 로직 (레슨 세대/버전, 유저, 대화, 학습, 문서, 콘텐츠)
│   ├── models/           # SQLAlchemy ORM 모델
│   ├── schemas/          # Pydantic 스키마 (lesson, auth, chat, learning)
│   ├── services/         # 콘텐츠 생성·문서 인덱싱 파이프라인 (Qdrant, OpenAI, 임베딩)
│   └── scripts/          # 시딩·이관·enrichment 스크립트
├── alembic/              # DB 스키마 마이그레이션
├── tests/                # pytest 테스트
├── index_data.py         # Qdrant 인덱싱 스크립트 (독립 실행)
└── validated_json_server.py  # 검증된 레슨 전용 별도 서버 (포트 8001)
```

생성된 레슨은 PostgreSQL `lessons`/`lesson_versions` 테이블에 세대(generation) 단위로 저장됩니다. (과거 파일 저장소 `../generated_content/`는 아카이브로만 보존)

