# LearnSphere API

React 학습 플랫폼 **LearnSphere**의 백엔드 API 서버입니다.

Qdrant(벡터 DB)에 인덱싱된 React 문서를 컨텍스트로 활용해 OpenAI LLM(`gpt-4o-mini`)으로 한국어 학습 콘텐츠(레슨)를 자동 생성하고, 생성된 레슨을 JSON 파일 + PostgreSQL 이력과 함께 관리·제공합니다.

## 주요 기능

- **레슨 자동 생성**: 레벨(초급/중급/고급)별로 Qdrant에서 토픽 컨텍스트를 수집하고, LLM으로 핵심 개념·코드 예시·퀴즈가 포함된 레슨 JSON을 생성 (백그라운드 실행)
- **레슨 제공 API**: 프론트엔드(Vite/CRA)를 위한 레슨 목차(`index.json`) 및 개별 레슨 조회
- **백업/복원**: 레슨 재생성 시 기존 파일을 날짜별 폴더로 자동 백업하고 DB에 이력 기록, 관리자 API로 개별/일괄 복원 지원
- **웹훅**: 원본 데이터 변경 이벤트 수신 시 콘텐츠 재생성 파이프라인 트리거

## 기술 스택

| 구분 | 기술 |
|---|---|
| 웹 프레임워크 | FastAPI + Uvicorn |
| 관계형 DB | PostgreSQL (SQLAlchemy) |
| 벡터 DB | Qdrant |
| LLM | OpenAI API (`gpt-4o-mini`) |
| 임베딩 | sentence-transformers |

## 빠른 시작

```bash
# 1. 의존성 설치 (uv가 .venv 생성 + uv.lock 기준으로 설치)
uv sync

# 2. 환경 변수 설정 (ENV_EXAMPLE.txt 참고하여 .env 생성)
#    DATABASE_URL, QDRANT_URL, QDRANT_API_KEY, OPENAI_API_KEY, ADMIN_API_KEY

# 3. PostgreSQL 실행 (Docker)
docker compose up -d              # postgres:16 컨테이너 시작 (healthy까지 대기)

# 4. DB 스키마 마이그레이션 (alembic)
uv run alembic upgrade head       # 신규 DB: 전체 테이블 생성
# (create_all 시절부터 쓰던 기존 DB는 최초 1회 `uv run alembic stamp 0001` 후 upgrade)

# 5. (최초 1회) 데이터 준비
uv run python index_data.py       # React 문서 → Qdrant 인덱싱
uv run python -m app.scripts.seed # 메타데이터 → PostgreSQL 시딩

# 6. 서버 실행 (포트 8000)
uv run uvicorn app.main:app --reload
```

서버 실행 후 http://127.0.0.1:8000/docs 에서 Swagger UI로 API를 확인할 수 있습니다.

> PostgreSQL은 `docker-compose.yml`로 실행합니다. 접속 정보(`user`/`password`/`learnsphere_db`/포트 5432)는 `.env`의 `POSTGRES_*`로 오버라이드할 수 있으며 `DATABASE_URL`과 일치해야 합니다. 자세한 내용은 [ARCHITECTURE.md §8.1](./ARCHITECTURE.md#81-postgresql-docker)을 참고하세요.

## 주요 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/health` | 헬스 체크 |
| GET | `/api/v1/lesson/index` | 레슨 목차 조회 |
| GET | `/api/v1/lesson/{filename}` | 개별 레슨 조회 |
| GET | `/api/v1/contents/{subject_name}` | 과목별 콘텐츠 메타데이터 조회 |
| POST | `/api/v1/admin/generate-all-content` | [관리자] 전체 레슨 재생성 (백그라운드) |
| GET | `/api/v1/admin/backup-list` | [관리자] 날짜별 백업 목록 조회 |
| POST | `/api/v1/admin/restore-lesson-backup` | [관리자] 백업본으로 레슨 복원 |

관리자 엔드포인트와 웹훅은 `X-Admin-API-Key` 헤더 인증이 필요합니다 (`.env`의 `ADMIN_API_KEY`).
전체 엔드포인트 목록은 [ARCHITECTURE.md](./ARCHITECTURE.md#5-api-엔드포인트)를 참고하세요.

## 프로젝트 구조

```
learnsphere-api/
├── app/
│   ├── main.py           # 앱 진입점 (라우터 등록, CORS, 정적 파일)
│   ├── api/              # API 라우터 (lesson, admin)
│   ├── core/             # DB 연결 설정
│   ├── crud/             # DB 조회 로직
│   ├── models/           # SQLAlchemy ORM 모델
│   ├── schemas/          # Pydantic 스키마
│   ├── services/         # 콘텐츠 생성 파이프라인 (Qdrant, OpenAI)
│   └── scripts/          # 시딩·마이그레이션 스크립트
├── index_data.py         # Qdrant 인덱싱 스크립트 (독립 실행)
└── validated_json_server.py  # 검증된 레슨 전용 별도 서버 (포트 8001)
```

생성된 레슨은 상위 폴더의 `../generated_content/`에 저장됩니다.

## 문서

- [ARCHITECTURE.md](./ARCHITECTURE.md) — 아키텍처, 데이터 흐름, DB 스키마, 전체 API 명세, 알려진 이슈
- [PROCESS_AND_RUN.md](./PROCESS_AND_RUN.md) — 상세 실행 방법 안내
