# 문서 업로드 → RAG 인덱싱 파이프라인 구현 계획

## 1. 배경

learnsphere-api에는 현재 React 문서 전용 오프라인 스크립트(`index_data.py`)만 있고, 임의 문서를 올려 RAG를 구축하는 경로가 없다. 이번 작업으로 관리자가 pdf/md/txt 문서를 API로 업로드하면 백그라운드에서 추출 → 청킹 → 임베딩 → Qdrant 인덱싱되는 파이프라인을 추가한다.

### 확정된 요구사항

| 항목 | 결정 |
|---|---|
| 지원 포맷 | pdf / md / txt만 (그 외 400) |
| 저장 위치 | **별도 Qdrant 컬렉션** — env `QDRANT_DOCS_COLLECTION` (기본 `uploaded-docs`). 기존 튜터 챗·레슨 생성 코드는 일절 변경 없음 |
| 권한 | **관리자 전용** — 기존 `verify_admin_key`(X-Admin-API-Key) 라우터 레벨 적용 |
| 처리 방식 | **백그라운드** — 202 즉시 응답, 상태 추적 DB 테이블 + 조회 API |
| 중복 정책 | 같은 파일명 **409 거부**, 교체는 DELETE 후 재업로드 |
| 인덱싱 | `recreate_collection` 금지, 문서 단위 upsert. point id는 결정적 `uuid5(document_id:chunk_idx)` |
| index_data.py | React 문서용으로 그대로 두고, 청킹 로직만 새 서비스에 일반화해 구현 |

## 2. 변경 파일

### 2-1. 의존성 (`pyproject.toml`)

```bash
uv add python-multipart pypdf
```

- `python-multipart` — FastAPI `UploadFile`(multipart/form-data) 파싱 필수
- `pypdf` — PDF 텍스트 추출 (순수 파이썬)

`ENV_EXAMPLE.txt`에 `QDRANT_DOCS_COLLECTION=uploaded-docs` 추가.

### 2-2. DB 모델 — `app/models/models.py` + `alembic/versions/0007_uploaded_documents.py`

`UploadedDocument` 테이블 (`uploaded_documents`):

- `id`(PK), `filename`(String 255, **unique** — 중복 409의 DB 레벨 근거), `file_type`, `file_size`
- `status`: pending / processing / completed / failed (server_default='pending')
- `chunk_count`, `error`(Text), `created_at`, `started_at`, `completed_at`

기존 `LessonGeneration` 상태 패턴을 따른다. 마이그레이션은 0006 스타일, `down_revision="0006"`.

### 2-3. CRUD — 신규 `app/crud/crud_documents.py`

`get_by_filename`, `get_document`, `list_documents`(created_at desc), `create_document`, `mark_processing`, `mark_completed`, `mark_failed`, `delete_document`. 각 상태 전이 함수는 commit 포함.

### 2-4. 서비스 — 신규 `app/services/document_service.py` (파이프라인 핵심)

재사용: `embedding_service.count_tokens / split_text_by_tokens / embed_texts / EMBEDDING_DIMENSION`, `qdrant_service.qdrant_client`(호출 시점 속성 접근 — 테스트 monkeypatch 호환).

상수: `DOCS_COLLECTION`(env), `CHUNK_MAX_TOKENS=2000`(index_data.py와 동일 근거), `MAX_FILE_SIZE=20MB`, `POINT_NAMESPACE=uuid5(NAMESPACE_URL, "learnsphere/uploaded-docs")`, `DocumentProcessingError` 예외.

| 함수 | 역할 |
|---|---|
| `get_extension(filename)` | 미지원 확장자 시 예외 (API에서 400으로 변환) |
| `extract_text(file_type, data)` | pdf: `pypdf.PdfReader`, md/txt: utf-8-sig → utf-8 decode. 빈 텍스트·손상 파일은 예외 래핑 |
| `chunk_text(text, title)` | index_data.py 로직 일반화: frontmatter 제거 → `'\n## '` 분할 → 헤더 `"제목: {title}\n\n"` 프리픽스 → `budget = 2000 - count_tokens(header)` → `split_text_by_tokens` |
| `point_id(document_id, chunk_idx)` | 결정적 uuid5 — 재시도 시 같은 id로 덮어쓰기 |
| `ensure_docs_collection()` | `collection_exists` 체크 후 생성(1536, COSINE) + **`document_id` INTEGER payload 인덱스** (Qdrant Cloud 삭제 필터에 필수) |
| `upsert_document_points(document_id, title, source, chunks)` | `embed_texts` → upsert(wait=True). payload: `{text, title, source, document_id, chunk_idx}` |
| `delete_document_points(document_id)` | FilterSelector로 문서 단위 삭제 |
| `process_document(document_id, filename, file_type, data, session_factory=SessionLocal)` | **BackgroundTask 진입점** — 아래 흐름 참고 |
| `remove_document(db, document)` | Qdrant 포인트 삭제 성공 후 DB 행 삭제. Qdrant 실패 시 예외 전파(행 유지 → 재시도 가능) |

`process_document` 흐름 (`content_pipeline_service.run_full_content_generation` 패턴 — 자체 세션 생성·finally close):

```
mark_processing → extract_text → chunk_text → ensure_docs_collection
→ upsert_document_points → mark_completed(chunk_count)
실패 시: 부분 포인트 정리(best-effort) → mark_failed(error 기록)
```

### 2-5. API — 신규 `app/api/documents_api.py` + `app/main.py` 등록 2줄

`router = APIRouter(dependencies=[Depends(verify_admin_key)])` (admin_api.py 패턴), 응답은 dict 헬퍼.

| 엔드포인트 | 동작 |
|---|---|
| `POST /admin/documents` (202) | 확장자 검증 400 → `await file.read()` 후 크기 검증(413 / 빈 파일 400) → 파일명 중복 409 (사전 조회 + IntegrityError 폴백) → 행 생성 → `background_tasks.add_task(process_document, ...)` → `{document_id, status}`. **bytes를 읽어서 태스크에 전달** (UploadFile은 응답 후 닫힘) |
| `GET /admin/documents` | 목록 |
| `GET /admin/documents/{id}` | 상태 조회, 없으면 404 |
| `DELETE /admin/documents/{id}` | 404 / Qdrant 실패 502(행 유지) / 성공 시 포인트+행 삭제 |

`main.py`: import + `app.include_router(documents_api.router, prefix="/api/v1")`.

## 3. Qdrant 컬렉션 설계

- 이름: env `QDRANT_DOCS_COLLECTION` (기본 `uploaded-docs`) — 기존 `QDRANT_COLLECTION`과 완전 분리
- 생성 시점: 첫 인덱싱 시 lazy 생성 (`collection_exists` 체크)
- 벡터: size 1536 (`EMBEDDING_DIMENSION`), COSINE
- payload: `{text, title, source(원본 파일명), document_id(int), chunk_idx(int)}`
- payload 인덱스: `document_id` INTEGER — 문서 단위 삭제 필터용 (index_data.py의 sub_category keyword 인덱스와 같은 이유)

## 4. 테스트 계획 — 신규 `tests/test_document_service.py`, `tests/test_documents_api.py`

기존 패턴 재사용: conftest `client`/`db_session`, 헤더 `X-Admin-API-Key: test-admin-key`, `QdrantClient(":memory:")` + monkeypatch(`qdrant_service.qdrant_client`, `EMBEDDING_DIMENSION=4`), `embed_texts` 스텁.

1. `chunk_text`(frontmatter·분할·프리픽스·budget), `point_id` 결정성, `extract_text`(txt/md 인코딩, 미지원 확장자, pdf 스텁)
2. `process_document` 성공 — completed + chunk_count + in-memory Qdrant 포인트/payload 검증 (`session_factory`로 테스트 세션 주입)
3. `process_document` 실패 — `EmbeddingError` 패치 → failed + error + 포인트 0개(정리 확인)
4. API 플로우 — 202/400/409/401/404, 목록·상세 (`process_document`는 몽키패치로 호출 여부만 검증)
5. DELETE — 포인트·행 삭제, 다른 문서 포인트 불변, 404

## 5. 구현 순서 및 검증

1. `uv add python-multipart pypdf`
2. 모델 + 마이그레이션 → `uv run alembic upgrade head`
3. crud → service → api → main.py 등록 → ENV_EXAMPLE.txt
4. 테스트 작성 → `uv run pytest`
5. 수동 검증: `uv run uvicorn app.main:app --reload` → Swagger(/docs)에서 X-Admin-API-Key 넣고 md 파일 업로드 → GET 상태가 completed 되는지 확인 → Qdrant Cloud 대시보드에서 `uploaded-docs` 컬렉션 포인트 확인 → DELETE 후 포인트 제거 확인

## 6. 리스크

- 대용량 파일 bytes를 메모리로 넘기는 구조 → `MAX_FILE_SIZE` 20MB 상한으로 방어
- 서버 재시작 시 pending/processing에 멈춘 문서는 자동 복구 없음 — 관리자가 삭제 후 재업로드 (기존 레슨 생성 세대와 동일한 한계)
