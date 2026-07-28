# 문서 업로드 RAG 파이프라인 — 단계별 구현 상세

> 상위 계획: `DOC_UPLOAD_PIPELINE_PLAN.md`
> 진행 방식: 각 Phase는 독립적으로 완료·검증 가능하며, 앞 Phase의 결과물 위에 기능을 쌓는다.
> Phase 순서 요약: 순수 로직(추출·청킹) → Qdrant 인덱싱 → DB 상태 추적 → 동기 업로드 API → 백그라운드 전환 + 조회 → 삭제 → PDF 지원 → 마무리 검증

---

## Phase 1 — 텍스트 추출·청킹 서비스 (md/txt, 외부 의존 없음)

가장 단순한 순수 함수부터. Qdrant·DB·API 없이 로직만 만들고 단위 테스트로 확정한다.

**작업**
1. 신규 `app/services/document_service.py` 생성:
   - 상수: `SUPPORTED_EXTENSIONS = {"md", "txt"}` (PDF는 Phase 7에서 추가), `CHUNK_MAX_TOKENS = 2000`, `DocumentProcessingError` 예외
   - `get_extension(filename) -> str` — 미지원 확장자 시 `DocumentProcessingError`
   - `extract_text(file_type, data: bytes) -> str` — utf-8-sig → utf-8 decode(errors="replace"). 빈 텍스트면 예외
   - `chunk_text(text, title) -> list[str]` — index_data.py 로직 일반화: frontmatter(`---` 2회 split) 제거 → `'\n## '` 분할 → 헤더 `"제목: {title}\n\n"` 프리픽스 → `budget = CHUNK_MAX_TOKENS - embedding_service.count_tokens(header)` → `embedding_service.split_text_by_tokens`
   - `point_id(document_id, chunk_idx) -> str` — `uuid5(POINT_NAMESPACE, f"{document_id}:{chunk_idx}")`, `POINT_NAMESPACE = uuid5(NAMESPACE_URL, "learnsphere/uploaded-docs")`
2. 신규 `tests/test_document_service.py` — 추출(인코딩·빈 파일·미지원 확장자), 청킹(frontmatter 제거·`## ` 분할·프리픽스·긴 섹션 budget 분할), `point_id` 결정성

**완료 기준**: `uv run pytest tests/test_document_service.py` 통과. API 호출 없음(tiktoken만 사용).

---

## Phase 2 — Qdrant 인덱싱·삭제 함수

Phase 1의 청크를 실제로 벡터 저장한다. 아직 API·DB 없음.

**작업**
1. `document_service.py`에 추가:
   - `DOCS_COLLECTION = os.getenv("QDRANT_DOCS_COLLECTION", "uploaded-docs")`
   - `ensure_docs_collection()` — `qdrant_service.qdrant_client`(호출 시점 속성 접근) `collection_exists` 체크 → 없으면 생성(size=`EMBEDDING_DIMENSION`, COSINE) + `document_id` INTEGER payload 인덱스(Qdrant Cloud 삭제 필터에 필수)
   - `upsert_document_points(document_id, title, source, chunks) -> int` — `embed_texts` → `PointStruct(id=point_id(...), payload={text, title, source, document_id, chunk_idx})` → `upsert(wait=True)`
   - `delete_document_points(document_id)` — `FilterSelector(document_id match)` 삭제, 컬렉션 미존재 시 no-op
2. `ENV_EXAMPLE.txt`에 `QDRANT_DOCS_COLLECTION=uploaded-docs` 추가
3. 테스트: `QdrantClient(":memory:")` + monkeypatch(`qdrant_service.qdrant_client`, `EMBEDDING_DIMENSION=4`, `embed_texts` 스텁) — upsert 후 포인트·payload 검증, 같은 문서 재-upsert 시 중복 없음(결정적 id), 삭제 시 다른 문서 포인트 불변

**완료 기준**: in-memory Qdrant 테스트 통과. 기존 `react-docs` 컬렉션 코드는 변경 없음.

---

## Phase 3 — DB 상태 추적 (모델·마이그레이션·CRUD)

업로드 이력·상태를 저장할 그릇을 만든다.

**작업**
1. `app/models/models.py`에 `UploadedDocument` 추가 (`uploaded_documents`): `id`, `filename`(unique), `file_type`, `file_size`, `status`(pending/processing/completed/failed, server_default='pending'), `chunk_count`, `error`, `created_at`, `started_at`, `completed_at` — `LessonGeneration` 상태 패턴 준용
2. `alembic/versions/0007_uploaded_documents.py` (`down_revision="0006"`, 0006 스타일) → `uv run alembic upgrade head`
3. 신규 `app/crud/crud_documents.py`: `get_by_filename`, `get_document`, `list_documents`(created_at desc), `create_document`, `mark_processing`, `mark_completed`, `mark_failed`, `delete_document` (상태 전이는 commit 포함)
4. 테스트: in-memory SQLite(`db_session` fixture)로 CRUD·상태 전이·filename unique 제약 검증

**완료 기준**: 마이그레이션 적용 성공, CRUD 테스트 통과.

---

## Phase 4 — 업로드 API (동기 처리 버전)

먼저 **동기**로 end-to-end를 연결해 전체 흐름을 검증한다. 백그라운드 전환은 Phase 5.

**작업**
1. `uv add python-multipart` (UploadFile 필수)
2. `document_service.py`에 `process_document(document_id, filename, file_type, data, session_factory=SessionLocal)` 추가:
   `mark_processing → extract_text → chunk_text → ensure_docs_collection → upsert_document_points → mark_completed(chunk_count)`, 실패 시 `delete_document_points`(best-effort) → `mark_failed(error)`. `content_pipeline_service.run_full_content_generation` 패턴(자체 세션·finally close)
3. 신규 `app/api/documents_api.py` — `router = APIRouter(dependencies=[Depends(verify_admin_key)])`:
   - `POST /admin/documents`: 확장자 400 → `await file.read()` 크기 검증(`MAX_FILE_SIZE=20MB` 413 / 빈 파일 400) → 파일명 중복 409(사전 조회 + IntegrityError 폴백) → 행 생성 → **이 Phase에서는 `process_document`를 직접 호출(동기)** → 최종 상태 반환
4. `app/main.py` 등록: import + `app.include_router(documents_api.router, prefix="/api/v1")`
5. 테스트: 202(또는 200)·400·409·401, `process_document` 성공/실패(EmbeddingError 패치 → failed + 포인트 정리) — Phase 2의 in-memory Qdrant fixture 재사용

**완료 기준**: Swagger에서 X-Admin-API-Key로 md 파일 업로드 → 응답에 completed + chunk_count 확인.

---

## Phase 5 — 백그라운드 전환 + 상태 조회 API

동기 흐름이 검증됐으니 BackgroundTasks로 전환하고 조회 수단을 붙인다.

**작업**
1. `POST /admin/documents`를 202 + `background_tasks.add_task(process_document, doc.id, doc.filename, doc.file_type, data)`로 전환 — **bytes를 읽어 태스크에 전달** (UploadFile은 응답 후 닫힘). 응답: `{"message", "document_id", "status": "pending"}`
2. `GET /admin/documents` — 목록(요약 dict: id, filename, file_type, file_size, status, chunk_count, error, 타임스탬프)
3. `GET /admin/documents/{id}` — 상태 조회, 없으면 404
4. 테스트: 업로드 202 + pending 행 생성(`process_document`는 몽키패치로 호출 인자만 검증), 목록·상세·404

**완료 기준**: 업로드 즉시 202 응답 → GET 폴링으로 pending → completed 전이 확인.

---

## Phase 6 — 삭제 API

중복 409 정책의 짝(교체 = 삭제 후 재업로드)을 완성한다.

**작업**
1. `document_service.remove_document(db, document)` — `delete_document_points` 성공 후 DB 행 삭제. Qdrant 실패 시 예외 전파(행 유지 → 재시도 가능)
2. `DELETE /admin/documents/{id}` — 404 / Qdrant 실패 502("벡터 삭제 실패 — 다시 시도하세요") / 성공 시 포인트+행 삭제
3. 테스트: 포인트 시드 후 삭제 → 포인트·행 모두 제거, 다른 문서 불변, 404, Qdrant 예외 시 502 + 행 유지

**완료 기준**: 삭제 → 같은 파일명 재업로드가 409 없이 성공.

---

## Phase 7 — PDF 지원

파이프라인이 안정된 뒤 포맷을 확장한다.

**작업**
1. `uv add pypdf`
2. `SUPPORTED_EXTENSIONS`에 `"pdf"` 추가, `extract_text`에 pdf 분기: `PdfReader(io.BytesIO(data))` 페이지별 `extract_text()` join. 손상 PDF·빈 텍스트는 `DocumentProcessingError` 래핑
3. 테스트: pdf 스텁(또는 최소 픽스처 bytes)로 추출·손상 파일 실패 케이스

**완료 기준**: 실제 PDF 업로드 → completed + 청크 확인.

---

## Phase 8 — 최종 검증·마무리

**작업**
1. `uv run pytest` 전체 통과 확인
2. 수동 E2E: `uv run uvicorn app.main:app --reload` → Swagger에서 md/txt/pdf 각각 업로드 → 상태 completed → Qdrant Cloud 대시보드에서 `uploaded-docs` 포인트 확인 → DELETE 후 포인트 제거 확인 → 미지원 확장자 400·중복 409·키 없음 401 확인
3. 기존 기능 회귀 확인: 튜터 챗 검색·레슨 생성이 업로드 문서의 영향을 받지 않는지 (별도 컬렉션이므로 코드상 영향 없음을 재확인)
4. `PROCESS_AND_RUN.md`에 문서 업로드 API 사용법 한 절 추가

**알려진 한계 (문서화만)**
- 서버 재시작 시 pending/processing에 멈춘 문서는 자동 복구 없음 — 관리자가 삭제 후 재업로드
- 파일 bytes를 메모리로 전달 — `MAX_FILE_SIZE` 20MB 상한으로 방어
