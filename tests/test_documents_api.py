# tests/test_documents_api.py
"""문서 업로드/관리 API 테스트.

인덱싱 본체(process_document)는 test_document_service.py에서 검증하므로,
여기서는 몽키패치로 호출 여부·인자만 확인하고 API 계약(상태 코드)에 집중한다.
"""
import pytest

from app.crud import crud_documents
from app.services import document_service

ADMIN_HEADERS = {"X-Admin-API-Key": "test-admin-key"}


@pytest.fixture()
def processed(monkeypatch):
    """process_document를 기록용 스텁으로 바꾼다 (실제 임베딩·Qdrant 호출 방지)."""
    calls = []

    def _record(document_id, filename, file_type, data, **kwargs):
        calls.append({
            "document_id": document_id, "filename": filename,
            "file_type": file_type, "data": data,
        })

    monkeypatch.setattr(document_service, "process_document", _record)
    return calls


def _upload(client, filename="guide.md", content=b"# hello", headers=ADMIN_HEADERS):
    return client.post(
        "/api/v1/admin/documents",
        files={"file": (filename, content, "text/markdown")},
        headers=headers or {})


# --- 업로드 ---

def test_upload_requires_admin_key(client, processed):
    assert _upload(client, headers=None).status_code == 401
    assert processed == []


def test_upload_accepts_and_starts_processing(client, db_session, processed):
    response = _upload(client)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"

    document = crud_documents.get_document(db_session, body["document_id"])
    assert document.filename == "guide.md"
    assert document.file_type == "md"
    assert document.file_size == len(b"# hello")

    assert len(processed) == 1
    assert processed[0]["document_id"] == document.id
    assert processed[0]["data"] == b"# hello"


def test_upload_rejects_unsupported_extension(client, processed):
    response = _upload(client, filename="slides.pptx")

    assert response.status_code == 400
    assert processed == []


def test_upload_rejects_empty_file(client, processed):
    response = _upload(client, content=b"")

    assert response.status_code == 400
    assert processed == []


def test_upload_rejects_oversized_file(client, processed, monkeypatch):
    monkeypatch.setattr(document_service, "MAX_FILE_SIZE", 10)

    response = _upload(client, content=b"x" * 11)

    assert response.status_code == 413
    assert processed == []


def test_upload_rejects_duplicate_filename(client, processed):
    assert _upload(client).status_code == 202

    response = _upload(client)

    assert response.status_code == 409
    assert len(processed) == 1  # 두 번째 업로드는 처리에 도달하지 않는다


# --- 조회 ---

def test_list_documents(client, db_session, processed):
    _upload(client)
    _upload(client, filename="notes.txt", content=b"note")

    response = client.get("/api/v1/admin/documents", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    filenames = [d["filename"] for d in response.json()]
    assert set(filenames) == {"guide.md", "notes.txt"}


def test_get_document_status(client, processed):
    document_id = _upload(client).json()["document_id"]

    response = client.get(
        f"/api/v1/admin/documents/{document_id}", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == document_id
    assert body["status"] == "pending"


def test_get_document_status_not_found(client):
    response = client.get("/api/v1/admin/documents/9999", headers=ADMIN_HEADERS)

    assert response.status_code == 404


# --- 삭제 ---

@pytest.fixture()
def docs_qdrant(monkeypatch):
    """in-memory Qdrant + 임베딩 스텁 (삭제 테스트는 실제 포인트가 필요하다)."""
    from qdrant_client import QdrantClient

    from app.services import embedding_service, qdrant_service

    qdrant = QdrantClient(":memory:")
    monkeypatch.setattr(qdrant_service, "qdrant_client", qdrant)
    monkeypatch.setattr(document_service, "DOCS_COLLECTION", "test-uploaded-docs")
    monkeypatch.setattr(embedding_service, "EMBEDDING_DIMENSION", 4)
    monkeypatch.setattr(
        embedding_service, "embed_texts", lambda texts: [[0.1] * 4 for _ in texts])
    return qdrant


def _point_count(qdrant, document_id=None):
    points, _ = qdrant.scroll(
        collection_name=document_service.DOCS_COLLECTION, limit=100,
        with_payload=True)
    if document_id is None:
        return len(points)
    return sum(1 for p in points if p.payload["document_id"] == document_id)


def test_delete_document_removes_points_and_row(client, db_session, docs_qdrant,
                                                processed):
    doc_id = _upload(client).json()["document_id"]
    other_id = _upload(client, filename="notes.txt", content=b"note").json()["document_id"]
    document_service.ensure_docs_collection()
    document_service.upsert_document_points(doc_id, "guide", "guide.md", ["A"])
    document_service.upsert_document_points(other_id, "notes", "notes.txt", ["B"])

    response = client.delete(
        f"/api/v1/admin/documents/{doc_id}", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert crud_documents.get_document(db_session, doc_id) is None
    assert _point_count(docs_qdrant, doc_id) == 0
    # 다른 문서의 포인트·행은 남아있다
    assert _point_count(docs_qdrant, other_id) == 1
    assert crud_documents.get_document(db_session, other_id) is not None


def test_delete_then_reupload_same_filename(client, docs_qdrant, processed):
    doc_id = _upload(client).json()["document_id"]

    assert client.delete(
        f"/api/v1/admin/documents/{doc_id}", headers=ADMIN_HEADERS).status_code == 200
    assert _upload(client).status_code == 202  # 409 없이 재업로드 성공


def test_delete_document_not_found(client):
    response = client.delete("/api/v1/admin/documents/9999", headers=ADMIN_HEADERS)

    assert response.status_code == 404


def test_delete_document_qdrant_failure_keeps_row(client, db_session,
                                                  processed, monkeypatch):
    doc_id = _upload(client).json()["document_id"]

    def _boom(document_id):
        raise RuntimeError("Qdrant 연결 실패")

    monkeypatch.setattr(document_service, "delete_document_points", _boom)

    response = client.delete(
        f"/api/v1/admin/documents/{doc_id}", headers=ADMIN_HEADERS)

    assert response.status_code == 502
    # DB 행이 남아 재시도할 수 있다
    assert crud_documents.get_document(db_session, doc_id) is not None
