# 문서 업로드 RAG — 다음 단계 작업 메모

> 선행 작업: `DOC_UPLOAD_PIPELINE_PLAN.md` → `doc_pipeline_detail.md` → `doc_pipeline_tasks.md` (2026-07-28 전 단계 완료)
> 이 문서는 완료된 파이프라인의 알려진 한계와, 이어서 진행할 수 있는 후속 작업을 정리한다.

## 1. 현재 상태 (완료된 것)

- 관리자가 pdf/md/txt를 업로드하면 백그라운드에서 추출 → 청킹 → 임베딩 → Qdrant 인덱싱
- 업로드 문서는 **전용 컬렉션**(`QDRANT_DOCS_COLLECTION`, 기본 `uploaded-docs`)에 격리 저장
- 관리 API: `POST/GET/DELETE /api/v1/admin/documents` (X-Admin-API-Key)
- **주의: 인덱싱만 되어 있고, 아직 아무 기능도 이 컬렉션을 검색하지 않는다** — 튜터 챗은 기존 React 문서 컬렉션(`QDRANT_COLLECTION`)만 본다

## 2. 알려진 한계 (현재 운영 규약)

| 한계 | 현재 대응 | 개선 아이디어 |
|---|---|---|
| 서버 재시작 시 pending/processing에 멈춘 문서는 자동 복구 없음 | 관리자가 상태 조회 후 DELETE → 재업로드 | 서버 기동 시(lifespan) processing 상태 문서를 failed로 전환하는 복구 훅 |
| 파일 bytes를 메모리로 전달 | `MAX_FILE_SIZE` 20MB 상한 | 대용량이 필요해지면 임시 파일 경유로 전환 |
| 업로드 문서가 검색에 활용되지 않음 | — | 아래 3번이 본 작업 |

## 3. 다음 단계: 튜터 챗에서 업로드 문서 검색 활용

### 목표
사용자가 튜터 챗에 질문하면 React 문서뿐 아니라 업로드된 문서에서도 근거를 찾아 답변한다.

### 구현 스케치

1. **검색 함수 추가** — `document_service.py`(또는 `qdrant_service.py`)에 업로드 컬렉션용 유사도 검색 추가:
   - `search_uploaded_docs(query: str, top_k: int) -> List[Dict]`
   - 기존 `qdrant_service.search_similar`와 동일한 반환 형태(`{text, title, source, score}`)로 맞추면 튜터 에이전트 수정이 최소화됨
   - payload에 `document_id`가 있으므로 상태가 completed인 문서만 검색되는 건 자동 보장(실패 문서는 포인트가 정리됨)

2. **튜터 에이전트 통합** — `app/agents/tutor_agent.py:97` 부근 (`docs = qdrant_service.search_similar(state["question"], top_k=TOP_K)`):
   - 두 컬렉션을 각각 검색한 뒤 score 기준으로 병합해 상위 TOP_K(현재 4)를 프롬프트에 싣는 방식이 가장 단순
   - 주의: 컬렉션이 달라도 같은 임베딩 모델(`text-embedding-3-small`)이라 score 비교 가능
   - 질의 임베딩을 두 번 만들지 않도록 `embed_query` 결과를 공유하는 리팩터 고려

3. **출처 표시** — 챗 응답의 sources에 업로드 문서 파일명이 노출되므로, 프론트에서 React 문서 출처와 구분할지 결정 필요 (payload `source`가 파일명이라 그대로 표시해도 무방)

4. **테스트** — `test_qdrant_search.py` 패턴 재사용: in-memory Qdrant에 두 컬렉션을 만들고 병합 검색이 score 순으로 상위 K를 반환하는지, 한쪽 컬렉션이 비어도 동작하는지 검증

### 결정이 필요한 것 (착수 전 확인)

- [ ] 병합 방식: 두 컬렉션 통합 상위 K vs React 문서 우선 + 업로드 문서 보조 (예: K개 중 최소 1자리 보장)
- [ ] 업로드 문서 검색을 항상 켤지, 레슨 컨텍스트가 없는 일반 질문에서만 켤지
- [ ] 레슨 생성 파이프라인은 계속 React 문서만 사용 (격리 유지 — 확정된 방침, 변경 없음)

## 4. 기타 후속 아이디어 (우선순위 낮음)

- 재시작 복구 훅: FastAPI lifespan에서 `status='processing'` 문서를 `failed`(error="서버 재시작으로 중단")로 일괄 전환
- 업로드 문서 목록/삭제를 위한 관리자 프론트 UI
- 같은 파일명 교체 업로드(덮어쓰기 모드) — 현재는 삭제 후 재업로드 규약
