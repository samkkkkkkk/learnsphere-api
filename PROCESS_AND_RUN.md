# learnshpere-api 백엔드 프로세스 및 실행 방법 안내

## 1. 주요 구성요소 및 데이터 흐름

- **FastAPI**: Python 기반의 고성능 웹 프레임워크로 API 서버를 구현합니다.
- **PostgreSQL**: 학습 콘텐츠 및 사용자 데이터를 저장하는 관계형 데이터베이스입니다.
- **Qdrant**: 벡터 검색을 위한 벡터 데이터베이스로, 문서 임베딩 및 유사도 검색에 사용됩니다.
- **OpenAI API**: LLM(대형 언어 모델)을 활용한 학습 자료 자동 생성에 사용됩니다.
- **환경 변수**: 데이터베이스, Qdrant, OpenAI 등 외부 서비스 연결 정보를 관리합니다.

### 데이터 흐름 요약
1. 사용자가 API를 통해 학습 요청을 보냅니다.
2. 서버는 Qdrant에서 관련 문서 임베딩을 검색합니다.
3. OpenAI API를 통해 LLM 기반 학습 자료를 생성합니다.
4. 결과를 DB에 저장하거나, 바로 응답으로 반환합니다.

## 2. 환경 변수 설명
- `DATABASE_URL`: PostgreSQL 접속 정보 (예: postgresql://user:password@localhost:5432/learnsphere_db)
- `QDRANT_URL`: Qdrant 서버 주소 (예: http://localhost:6333)
- `QDRANT_API_KEY`: Qdrant API 인증키
- `OPENAI_API_KEY`: OpenAI API 인증키

> 예시 파일: `ENV_EXAMPLE.txt` 참고

## 3. 설치 및 실행 방법

### 1) 의존성 설치
[uv](https://docs.astral.sh/uv/)로 의존성을 관리합니다. 직접 의존성은 `pyproject.toml`, 전체 버전 고정은 `uv.lock`에 기록됩니다.
```bash
uv sync
```

### 2) 환경 변수 파일 생성
- `ENV_EXAMPLE.txt`를 참고하여 `.env` 파일을 생성하고, 실제 값을 입력합니다.

### 3) 데이터베이스 준비
- PostgreSQL을 설치하고, 지정한 DB와 계정을 생성합니다.

### 4) 서버 실행
```bash
uv run uvicorn app.main:app --reload
```
- 서버가 실행되면: http://127.0.0.1:8000/docs 에서 API 문서를 확인할 수 있습니다.

## 4. 기타
- Qdrant, OpenAI 등 외부 서비스가 정상적으로 동작해야 전체 기능이 작동합니다.
- 추가 데이터 인덱싱, 백업, 마이그레이션 등은 `app/scripts/` 폴더의 스크립트를 참고하세요. 