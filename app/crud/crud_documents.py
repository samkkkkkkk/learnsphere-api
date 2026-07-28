# app/crud/crud_documents.py
"""업로드 문서(uploaded_documents) CRUD.

상태 전이(mark_*)는 BackgroundTask가 자체 세션으로 호출하므로 commit을 포함한다.
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.models import UploadedDocument


def get_by_filename(db: Session, filename: str) -> Optional[UploadedDocument]:
    return (db.query(UploadedDocument)
            .filter(UploadedDocument.filename == filename)
            .first())


def get_document(db: Session, document_id: int) -> Optional[UploadedDocument]:
    return db.get(UploadedDocument, document_id)


def list_documents(db: Session) -> List[UploadedDocument]:
    return (db.query(UploadedDocument)
            .order_by(UploadedDocument.created_at.desc(),
                      UploadedDocument.id.desc())
            .all())


def create_document(db: Session, filename: str, file_type: str,
                    file_size: int) -> UploadedDocument:
    document = UploadedDocument(
        filename=filename, file_type=file_type, file_size=file_size)
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def mark_processing(db: Session, document_id: int) -> None:
    document = get_document(db, document_id)
    document.status = 'processing'
    document.started_at = datetime.now()
    db.commit()


def mark_completed(db: Session, document_id: int, chunk_count: int) -> None:
    document = get_document(db, document_id)
    document.status = 'completed'
    document.chunk_count = chunk_count
    document.completed_at = datetime.now()
    db.commit()


def mark_failed(db: Session, document_id: int, error: str) -> None:
    document = get_document(db, document_id)
    document.status = 'failed'
    document.error = error[:2000]
    document.completed_at = datetime.now()
    db.commit()


def delete_document(db: Session, document: UploadedDocument) -> None:
    db.delete(document)
    db.commit()
