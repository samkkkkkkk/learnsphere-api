# 문서 업로드 RAG 파이프라인 — 작업 체크리스트

> 상세 계획: `doc_pipeline_detail.md` / 상위 계획: `DOC_UPLOAD_PIPELINE_PLAN.md`
> 각 Phase의 마지막 항목(✅ 완료 기준)을 통과해야 다음 Phase로 진행한다.

## Phase 1 — 텍스트 추출·청킹 서비스 (md/txt)

- [x] P1-1. `app/services/document_service.py` 생성 — 상수 정의: `SUPPORTED_EXTENSIONS = {"md", "txt"}`, `CHUNK_MAX_TOKENS = 2000`, `POINT_NAMESPACE`, `DocumentProcessingError` 예외
- [x] P1-2. `get_extension(filename)` 구현 — 미지원 확장자 시 `DocumentProcessingError`
- [x] P1-3. `extract_text(file_type, data)` 구현 — utf-8-sig → utf-8 decode, 빈 텍스트 예외
- [x] P1-4. `chunk_text(text, title)` 구현 — frontmatter 제거 → `'\n## '` 분할 → `"제목: {title}\n\n"` 프리픽스 → budget 계산 → `split_text_by_tokens`
- [x] P1-5. `point_id(document_id, chunk_idx)` 구현 — 결정적 uuid5
- [x] P1-6. `tests/test_document_service.py` 작성 — 추출(인코딩·빈 파일·미지원 확장자), 청킹(frontmatter·분할·프리픽스·budget), `point_id` 결정성
- [x] ✅ P1 완료 기준: `uv run pytest tests/test_document_service.py` 통과

## Phase 2 — Qdrant 인덱싱·삭제 함수

- [x] P2-1. `DOCS_COLLECTION` env 상수 추가 (`QDRANT_DOCS_COLLECTION`, 기본 `uploaded-docs`)
- [x] P2-2. `ensure_docs_collection()` 구현 — `collection_exists` 체크, 생성(1536·COSINE) + `document_id` INTEGER payload 인덱스
- [x] P2-3. `upsert_document_points(document_id, title, source, chunks)` 구현 — `embed_texts` → 결정적 id upsert(wait=True), payload `{text, title, source, document_id, chunk_idx}`
- [x] P2-4. `delete_document_points(document_id)` 구현 — FilterSelector 삭제, 컬렉션 미존재 no-op
- [x] P2-5. `ENV_EXAMPLE.txt`에 `QDRANT_DOCS_COLLECTION=uploaded-docs` 추가
- [x] P2-6. 테스트 — in-memory Qdrant fixture(`qdrant_client`·`EMBEDDING_DIMENSION=4`·`embed_texts` 스텁 monkeypatch): upsert 포인트·payload 검증, 재-upsert 중복 없음, 삭제 시 다른 문서 불변
- [x] ✅ P2 완료 기준: in-memory Qdrant 테스트 통과, 기존 react-docs 경로 무변경

## Phase 3 — DB 상태 추적

- [x] P3-1. `app/models/models.py`에 `UploadedDocument` 모델 추가 (filename unique, status server_default='pending')
- [x] P3-2. `alembic/versions/0007_uploaded_documents.py` 작성 (`down_revision="0006"`)
- [x] P3-3. `uv run alembic upgrade head` 적용 확인
- [x] P3-4. `app/crud/crud_documents.py` 작성 — `get_by_filename` / `get_document` / `list_documents` / `create_document` / `mark_processing` / `mark_completed` / `mark_failed` / `delete_document`
- [x] P3-5. 테스트 — CRUD·상태 전이·filename unique 제약 (in-memory SQLite)
- [x] ✅ P3 완료 기준: 마이그레이션 적용 성공 + CRUD 테스트 통과

## Phase 4 — 업로드 API (동기 처리)

- [x] P4-1. `uv add python-multipart`
- [x] P4-2. `process_document(document_id, filename, file_type, data, session_factory=SessionLocal)` 구현 — mark_processing → 추출 → 청킹 → ensure → upsert → mark_completed, 실패 시 포인트 정리 + mark_failed
- [x] P4-3. `app/api/documents_api.py` 생성 — `APIRouter(dependencies=[Depends(verify_admin_key)])`
- [x] P4-4. `POST /admin/documents` 구현 (동기 버전) — 확장자 400 → 크기 413/빈 파일 400 → 중복 409(사전 조회 + IntegrityError 폴백) → 행 생성 → `process_document` 직접 호출 → 최종 상태 반환
- [x] P4-5. `app/main.py`에 라우터 등록 (import + include_router)
- [x] P4-6. 테스트 — 400/409/401, `process_document` 성공(completed + chunk_count + 포인트 검증)/실패(EmbeddingError → failed + 포인트 정리)
- [x] ✅ P4 완료 기준: Swagger에서 md 업로드 → completed + chunk_count 확인

## Phase 5 — 백그라운드 전환 + 상태 조회 API

- [x] P5-1. `POST /admin/documents`를 202 + `background_tasks.add_task(...)`로 전환 (bytes를 태스크에 전달)
- [x] P5-2. `GET /admin/documents` 목록 구현 (요약 dict 헬퍼)
- [x] P5-3. `GET /admin/documents/{id}` 상태 조회 구현 (404 포함)
- [x] P5-4. 테스트 — 업로드 202 + pending 행(process_document 몽키패치로 인자 검증), 목록·상세·404
- [x] ✅ P5 완료 기준: 업로드 즉시 202 → GET 폴링으로 pending → completed 전이 확인

## Phase 6 — 삭제 API

- [x] P6-1. `remove_document(db, document)` 구현 — Qdrant 삭제 성공 후 DB 행 삭제, Qdrant 실패 시 예외 전파
- [x] P6-2. `DELETE /admin/documents/{id}` 구현 — 404 / Qdrant 실패 502(행 유지) / 성공 시 포인트+행 삭제
- [x] P6-3. 테스트 — 포인트·행 제거, 다른 문서 불변, 404, Qdrant 예외 시 502 + 행 유지
- [x] ✅ P6 완료 기준: 삭제 후 같은 파일명 재업로드가 409 없이 성공

## Phase 7 — PDF 지원

- [x] P7-1. `uv add pypdf`
- [x] P7-2. `SUPPORTED_EXTENSIONS`에 `"pdf"` 추가 + `extract_text` pdf 분기 (`PdfReader`, 손상·빈 텍스트는 `DocumentProcessingError` 래핑)
- [x] P7-3. 테스트 — pdf 추출 성공·손상 파일 실패 케이스
- [x] ✅ P7 완료 기준: 실제 PDF 업로드 → completed + 청크 확인 (테스트로 검증, 실물 PDF 수동 확인은 선택)

## Phase 8 — 최종 검증·마무리

- [x] P8-1. `uv run pytest` 전체 통과 (209 passed)
- [x] P8-2. 수동 E2E — 로컬 서버 기동 후 실제 md 업로드 → OpenAI 임베딩 → Qdrant Cloud 인덱싱 completed(2청크) → DELETE 후 404 확인 (2026-07-28)
- [x] P8-3. 에러 경로 확인 — 중복 409, 키 없음 401, 삭제 후 재조회 404 실측 확인
- [x] P8-4. 기존 기능 회귀 확인 — 별도 컬렉션 사용, 기존 qdrant_service/튜터 챗/레슨 생성 코드 무변경 (전체 테스트 통과로 검증)
- [x] ✅ P8 완료 기준: 전체 테스트 + 수동 E2E + 회귀 확인 완료
- [x] P8-5. `PROCESS_AND_RUN.md`에 문서 업로드 API 사용법 추가
