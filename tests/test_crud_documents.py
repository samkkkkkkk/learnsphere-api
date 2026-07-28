# tests/test_crud_documents.py
"""업로드 문서 CRUD·상태 전이 테스트 (in-memory SQLite)."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.crud import crud_documents


@pytest.fixture()
def document(db_session):
    return crud_documents.create_document(
        db_session, filename="guide.md", file_type="md", file_size=1024)


def test_create_document_defaults(document):
    assert document.status == "pending"
    assert document.chunk_count is None
    assert document.error is None
    assert document.created_at is not None


def test_filename_unique_constraint(db_session, document):
    with pytest.raises(IntegrityError):
        crud_documents.create_document(
            db_session, filename="guide.md", file_type="md", file_size=10)
    db_session.rollback()


def test_get_by_filename(db_session, document):
    assert crud_documents.get_by_filename(db_session, "guide.md").id == document.id
    assert crud_documents.get_by_filename(db_session, "없는파일.md") is None


def test_list_documents_latest_first(db_session, document):
    second = crud_documents.create_document(
        db_session, filename="notes.txt", file_type="txt", file_size=10)

    documents = crud_documents.list_documents(db_session)
    assert [d.id for d in documents] == [second.id, document.id]


def test_status_transitions(db_session, document):
    crud_documents.mark_processing(db_session, document.id)
    assert document.status == "processing"
    assert document.started_at is not None

    crud_documents.mark_completed(db_session, document.id, chunk_count=5)
    assert document.status == "completed"
    assert document.chunk_count == 5
    assert document.completed_at is not None


def test_mark_failed_records_error(db_session, document):
    crud_documents.mark_failed(db_session, document.id, error="임베딩 실패")
    assert document.status == "failed"
    assert document.error == "임베딩 실패"
    assert document.completed_at is not None


def test_delete_document(db_session, document):
    crud_documents.delete_document(db_session, document)
    assert crud_documents.get_document(db_session, document.id) is None
