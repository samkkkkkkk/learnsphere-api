# app/services/document_service.py
"""업로드 문서 인덱싱 파이프라인 (추출 → 청킹 → 임베딩 → Qdrant).

업로드 문서는 React 문서 컬렉션과 분리된 전용 컬렉션(DOCS_COLLECTION)에 저장한다.
튜터 챗·레슨 생성은 기존 컬렉션만 보므로 업로드 문서의 영향을 받지 않는다.

point id는 (document_id, chunk_idx) 기반 결정적 uuid5다 — 같은 문서를 재처리해도
새 포인트가 쌓이지 않고 덮어써진다.
"""
import io
import os
import uuid

from pypdf import PdfReader
from qdrant_client.http import models as qmodels

from . import embedding_service, qdrant_service
from ..core.database import SessionLocal
from ..crud import crud_documents

DOCS_COLLECTION = os.getenv("QDRANT_DOCS_COLLECTION", "uploaded-docs")

SUPPORTED_EXTENSIONS = {"pdf", "md", "txt"}

# index_data.py와 같은 근거 — 검색이 청크 여러 개를 프롬프트에 싣기 때문에,
# 청크가 크면 답변 한 번의 토큰 비용이 그만큼 커진다.
CHUNK_MAX_TOKENS = 2000

MAX_FILE_SIZE = 20 * 1024 * 1024  # bytes를 메모리로 다루므로 상한이 필요하다

POINT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "learnsphere/uploaded-docs")


class DocumentProcessingError(Exception):
    """문서 처리 실패 (미지원 포맷, 추출 실패 등)."""


def get_extension(filename: str) -> str:
    """소문자 확장자를 반환한다. 미지원 포맷이면 예외."""
    if "." not in filename:
        raise DocumentProcessingError(
            f"확장자가 없는 파일입니다. 지원 포맷: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentProcessingError(
            f"지원하지 않는 포맷입니다({extension}). "
            f"지원 포맷: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    return extension


def extract_text(file_type: str, data: bytes) -> str:
    """파일 bytes에서 본문 텍스트를 뽑는다."""
    if file_type not in SUPPORTED_EXTENSIONS:
        raise DocumentProcessingError(f"지원하지 않는 포맷입니다: {file_type}")

    if file_type == "pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join(
                page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise DocumentProcessingError(
                f"PDF를 읽을 수 없습니다: {exc}") from exc
    else:
        # utf-8-sig는 BOM이 있으면 제거하고 없으면 일반 utf-8과 동일하게 동작한다
        text = data.decode("utf-8-sig", errors="replace")

    if not text.strip():
        raise DocumentProcessingError("추출된 텍스트가 없습니다.")
    return text


def chunk_text(text: str, title: str) -> list:
    """본문을 임베딩 가능한 청크들로 나눈다.

    index_data.py의 React 문서 청킹을 일반화한 것: frontmatter 제거 →
    '## ' 소제목 분할 → 제목 헤더 프리픽스 → 토큰 예산 내로 재분할.
    """
    content_parts = text.split("---", 2)
    actual_content = (content_parts[2].strip()
                      if len(content_parts) > 2 else text.strip())

    # 검색 정확도를 높이기 위해 메타데이터를 청크 머리에 붙인다
    header = f"제목: {title}\n\n"
    budget = CHUNK_MAX_TOKENS - embedding_service.count_tokens(header)

    chunks = []
    for i, section in enumerate(actual_content.split("\n## ")):
        section_text = section.strip()
        if not section_text:
            continue
        if i > 0:
            section_text = f"## {section_text}"
        for part in embedding_service.split_text_by_tokens(section_text, budget):
            chunks.append(header + part)
    return chunks


def point_id(document_id: int, chunk_idx: int) -> str:
    """결정적 포인트 id — 재처리 시 같은 id로 덮어써져 중복이 쌓이지 않는다."""
    return str(uuid.uuid5(POINT_NAMESPACE, f"{document_id}:{chunk_idx}"))


# --- Qdrant 인덱싱 ---

def ensure_docs_collection() -> None:
    """업로드 문서 컬렉션이 없으면 만든다 (기존 데이터는 건드리지 않는다)."""
    client = qdrant_service.qdrant_client
    if client.collection_exists(DOCS_COLLECTION):
        return
    client.create_collection(
        collection_name=DOCS_COLLECTION,
        vectors_config=qmodels.VectorParams(
            size=embedding_service.EMBEDDING_DIMENSION,
            distance=qmodels.Distance.COSINE,
        ),
    )
    # Qdrant Cloud는 payload 필터(문서 단위 삭제)에 인덱스가 필요하다.
    # (in-memory 모드는 인덱스 없이도 동작하므로 테스트에서는 드러나지 않음)
    client.create_payload_index(
        collection_name=DOCS_COLLECTION,
        field_name="document_id",
        field_schema=qmodels.PayloadSchemaType.INTEGER,
    )


def upsert_document_points(document_id: int, title: str, source: str,
                           chunks: list) -> int:
    """청크들을 임베딩해 컬렉션에 적재한다. 적재한 청크 수를 반환."""
    vectors = embedding_service.embed_texts(chunks)
    qdrant_service.qdrant_client.upsert(
        collection_name=DOCS_COLLECTION,
        points=[
            qmodels.PointStruct(
                id=point_id(document_id, i),
                vector=vector,
                payload={
                    "text": chunk,
                    "title": title,
                    "source": source,
                    "document_id": document_id,
                    "chunk_idx": i,
                },
            )
            for i, (chunk, vector) in enumerate(zip(chunks, vectors))
        ],
        wait=True,
    )
    return len(chunks)


def process_document(document_id: int, filename: str, file_type: str,
                     data: bytes, session_factory=SessionLocal) -> None:
    """업로드 문서 하나를 인덱싱한다 — BackgroundTask 진입점.

    요청 스코프 밖에서 실행되므로 세션을 직접 만든다
    (content_pipeline_service.run_full_content_generation과 같은 패턴).
    실패하면 부분 적재된 포인트를 정리하고 상태를 failed로 남긴다.
    """
    db = session_factory()
    try:
        crud_documents.mark_processing(db, document_id)
        text = extract_text(file_type, data)
        title = filename.rsplit(".", 1)[0]
        chunks = chunk_text(text, title)
        if not chunks:
            raise DocumentProcessingError("인덱싱할 청크가 없습니다.")
        ensure_docs_collection()
        chunk_count = upsert_document_points(document_id, title, filename, chunks)
        crud_documents.mark_completed(db, document_id, chunk_count)
        print(f"✅ [Docs] '{filename}' 인덱싱 완료 ({chunk_count} 청크)")
    except Exception as exc:
        db.rollback()
        try:
            delete_document_points(document_id)  # 부분 적재 정리 (멱등)
        except Exception as cleanup_exc:
            print(f"⚠️ [Docs] 부분 포인트 정리 실패(무시): {cleanup_exc}")
        crud_documents.mark_failed(db, document_id, error=str(exc))
        print(f"❌ [Docs] '{filename}' 인덱싱 실패: {exc}")
    finally:
        db.close()


def remove_document(db, document) -> None:
    """문서의 Qdrant 포인트와 DB 행을 지운다.

    Qdrant 삭제가 실패하면 예외를 전파하고 DB 행을 남긴다 — 재시도할 수 있도록.
    """
    delete_document_points(document.id)
    crud_documents.delete_document(db, document)


def delete_document_points(document_id: int) -> None:
    """한 문서의 포인트 전부를 지운다. 컬렉션이 없으면 아무 것도 안 한다."""
    client = qdrant_service.qdrant_client
    if not client.collection_exists(DOCS_COLLECTION):
        return
    client.delete(
        collection_name=DOCS_COLLECTION,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(must=[
                qmodels.FieldCondition(
                    key="document_id",
                    match=qmodels.MatchValue(value=document_id),
                )
            ])
        ),
        wait=True,
    )
