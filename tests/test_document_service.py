# tests/test_document_service.py
"""업로드 문서 파이프라인 서비스 테스트.

추출·청킹은 tiktoken만 쓰는 순수 로직이라 외부 호출 없이 검증한다.
인덱싱은 in-memory Qdrant + 임베딩 스텁으로 검증한다 (test_qdrant_search.py 패턴).
"""
import pytest
from qdrant_client import QdrantClient

from app.services import document_service, embedding_service, qdrant_service

VECTOR_SIZE = 4


# --- 추출 ---

def test_get_extension_supported():
    assert document_service.get_extension("guide.MD") == "md"
    assert document_service.get_extension("notes.txt") == "txt"
    assert document_service.get_extension("report.pdf") == "pdf"


def test_get_extension_unsupported():
    with pytest.raises(document_service.DocumentProcessingError):
        document_service.get_extension("slides.pptx")


def test_get_extension_missing():
    with pytest.raises(document_service.DocumentProcessingError):
        document_service.get_extension("README")


def test_extract_text_utf8():
    assert document_service.extract_text("txt", "안녕하세요".encode("utf-8")) == "안녕하세요"


def test_extract_text_utf8_bom():
    data = "# 제목".encode("utf-8-sig")
    assert document_service.extract_text("md", data) == "# 제목"


def test_extract_text_empty_raises():
    with pytest.raises(document_service.DocumentProcessingError):
        document_service.extract_text("txt", b"   \n  ")


def test_extract_text_pdf_joins_pages(monkeypatch):
    class _FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class _FakeReader:
        def __init__(self, stream):
            self.pages = [_FakePage("1쪽 내용"), _FakePage("2쪽 내용")]

    monkeypatch.setattr(document_service, "PdfReader", _FakeReader)

    assert document_service.extract_text("pdf", b"%PDF-") == "1쪽 내용\n\n2쪽 내용"


def test_extract_text_pdf_corrupt_raises():
    with pytest.raises(document_service.DocumentProcessingError):
        document_service.extract_text("pdf", b"this is not a pdf")


def test_extract_text_pdf_blank_pages_raises():
    """텍스트 없는 PDF(스캔본 등)는 인덱싱할 수 없다는 오류를 낸다."""
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)

    with pytest.raises(document_service.DocumentProcessingError):
        document_service.extract_text("pdf", buffer.getvalue())


# --- 청킹 ---

def test_chunk_text_prefixes_title_header():
    chunks = document_service.chunk_text("본문 내용입니다.", "가이드")

    assert len(chunks) == 1
    assert chunks[0].startswith("제목: 가이드\n\n")
    assert "본문 내용입니다." in chunks[0]


def test_chunk_text_strips_frontmatter():
    text = "---\ntitle: x\n---\n실제 본문"
    chunks = document_service.chunk_text(text, "문서")

    assert len(chunks) == 1
    assert "title: x" not in chunks[0]
    assert "실제 본문" in chunks[0]


def test_chunk_text_splits_on_h2():
    text = "도입부\n## 첫 번째\n내용1\n## 두 번째\n내용2"
    chunks = document_service.chunk_text(text, "문서")

    assert len(chunks) == 3
    # 첫 번째가 아닌 섹션에는 '## '가 다시 붙는다
    assert "## 첫 번째" in chunks[1]
    assert "## 두 번째" in chunks[2]


def test_chunk_text_respects_token_budget():
    # 한 섹션이 예산(2000 - 헤더)을 넘으면 문단 경계로 더 나뉜다
    long_paragraphs = "\n\n".join(["word " * 800] * 4)  # 총 ~3200 토큰 — 예산 초과
    chunks = document_service.chunk_text(long_paragraphs, "문서")

    assert len(chunks) >= 2
    for chunk in chunks:
        assert embedding_service.count_tokens(chunk) <= document_service.CHUNK_MAX_TOKENS
        assert chunk.startswith("제목: 문서\n\n")


def test_chunk_text_empty_returns_no_chunks():
    assert document_service.chunk_text("   ", "문서") == []


# --- point id ---

def test_point_id_deterministic():
    assert (document_service.point_id(1, 0)
            == document_service.point_id(1, 0))


def test_point_id_distinct_per_chunk_and_document():
    ids = {
        document_service.point_id(1, 0),
        document_service.point_id(1, 1),
        document_service.point_id(2, 0),
    }
    assert len(ids) == 3


# --- Qdrant 인덱싱 ---

@pytest.fixture()
def docs_qdrant(monkeypatch):
    """in-memory Qdrant + 임베딩 스텁. 컬렉션은 ensure_docs_collection이 만든다."""
    client = QdrantClient(":memory:")
    monkeypatch.setattr(qdrant_service, "qdrant_client", client)
    monkeypatch.setattr(document_service, "DOCS_COLLECTION", "test-uploaded-docs")
    monkeypatch.setattr(embedding_service, "EMBEDDING_DIMENSION", VECTOR_SIZE)
    monkeypatch.setattr(
        embedding_service, "embed_texts",
        lambda texts: [[0.1] * VECTOR_SIZE for _ in texts])
    return client


def _all_points(client):
    points, _ = client.scroll(
        collection_name=document_service.DOCS_COLLECTION, limit=100,
        with_payload=True)
    return points


def test_ensure_docs_collection_creates_once(docs_qdrant):
    document_service.ensure_docs_collection()
    document_service.ensure_docs_collection()  # 두 번째 호출은 no-op

    assert docs_qdrant.collection_exists(document_service.DOCS_COLLECTION)


def test_upsert_document_points_stores_payload(docs_qdrant):
    document_service.ensure_docs_collection()

    count = document_service.upsert_document_points(
        7, "가이드", "guide.md", ["청크 하나", "청크 둘"])

    assert count == 2
    points = _all_points(docs_qdrant)
    assert len(points) == 2
    payloads = {p.payload["chunk_idx"]: p.payload for p in points}
    assert payloads[0] == {
        "text": "청크 하나", "title": "가이드", "source": "guide.md",
        "document_id": 7, "chunk_idx": 0,
    }


def test_upsert_same_document_no_duplicates(docs_qdrant):
    """결정적 point id 덕에 재처리해도 포인트가 쌓이지 않는다."""
    document_service.ensure_docs_collection()

    document_service.upsert_document_points(7, "가이드", "guide.md", ["A", "B"])
    document_service.upsert_document_points(7, "가이드", "guide.md", ["A2", "B2"])

    points = _all_points(docs_qdrant)
    assert len(points) == 2
    assert {p.payload["text"] for p in points} == {"A2", "B2"}


def test_delete_document_points_keeps_other_documents(docs_qdrant):
    document_service.ensure_docs_collection()
    document_service.upsert_document_points(7, "가이드", "guide.md", ["A"])
    document_service.upsert_document_points(8, "노트", "notes.txt", ["B"])

    document_service.delete_document_points(7)

    points = _all_points(docs_qdrant)
    assert len(points) == 1
    assert points[0].payload["document_id"] == 8


def test_delete_document_points_without_collection_is_noop(docs_qdrant):
    # 컬렉션을 만들지 않은 상태 — 예외 없이 지나가야 한다
    document_service.delete_document_points(1)


# --- process_document (BackgroundTask 진입점) ---

@pytest.fixture()
def uploaded_doc(db_session):
    from app.crud import crud_documents

    return crud_documents.create_document(
        db_session, filename="guide.md", file_type="md", file_size=100)


def _reload(db_session, document_id):
    """process_document가 세션을 close하므로 refresh 대신 재조회한다."""
    from app.crud import crud_documents

    return crud_documents.get_document(db_session, document_id)


def test_process_document_success(docs_qdrant, db_session, uploaded_doc):
    doc_id = uploaded_doc.id  # close 후에는 인스턴스 속성 접근이 불가하므로 미리 캡처
    data = "도입부\n## 섹션\n내용".encode("utf-8")

    document_service.process_document(
        doc_id, "guide.md", "md", data,
        session_factory=lambda: db_session)

    uploaded_doc = _reload(db_session, doc_id)
    assert uploaded_doc.status == "completed"
    assert uploaded_doc.chunk_count == 2
    assert uploaded_doc.started_at is not None
    assert uploaded_doc.completed_at is not None

    points = _all_points(docs_qdrant)
    assert len(points) == 2
    assert all(p.payload["title"] == "guide" for p in points)
    assert all(p.payload["source"] == "guide.md" for p in points)


def test_process_document_embedding_failure(docs_qdrant, db_session,
                                            uploaded_doc, monkeypatch):
    def _boom(texts):
        raise embedding_service.EmbeddingError("임베딩 실패")

    monkeypatch.setattr(embedding_service, "embed_texts", _boom)
    doc_id = uploaded_doc.id

    document_service.process_document(
        doc_id, "guide.md", "md", "본문".encode("utf-8"),
        session_factory=lambda: db_session)

    uploaded_doc = _reload(db_session, doc_id)
    assert uploaded_doc.status == "failed"
    assert "임베딩 실패" in uploaded_doc.error
    # 부분 적재 정리 — 포인트가 남아있지 않다
    assert _all_points(docs_qdrant) == []


def test_process_document_empty_text_fails(docs_qdrant, db_session,
                                           uploaded_doc):
    doc_id = uploaded_doc.id

    document_service.process_document(
        doc_id, "guide.md", "md", b"   ",
        session_factory=lambda: db_session)

    uploaded_doc = _reload(db_session, doc_id)
    assert uploaded_doc.status == "failed"
    assert uploaded_doc.error
